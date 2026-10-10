"""Offline rc11 CPU replay with charged native and screenshot latency.

This is a simulated IO boundary, never game input or live visual verification.
"""
from test_support import read_local_fixture_text
from test_support import load_local_palette_session
import copy,json,time,unittest
from pathlib import Path
from unittest.mock import patch
import test_native_live_controller as io_fixture
import test_native_refinement_controller as controller_fixture
from native_input_compile import native_drag_gesture
from native_input_response import InputSettings,InputGeometry,replay_native_route
from native_palette_scoring import load_session,score_native_pose
from native_live.controller import run_goal_loop
from native_live import refinement
from native_live.project_closed_loop_io import InputNotStarted

FIXTURE=Path(__file__).parent/'fixtures/native_live/rc11_refinement'
ARTIFACTS=Path(__file__).resolve().parents[2]/'outputs/native-integration/verification/rc12-protected-refinement/recorded'


class RecordedIO(io_fixture.FixtureIO):
    def __init__(self):
        self.case=json.loads(read_local_fixture_text(FIXTURE/'case.json', encoding='utf-8'))
        self.cp=copy.deepcopy(self.case['initial']);self.session=load_local_palette_session(FIXTURE/'palette')
        self.settings=InputSettings(**self.case['settings']);self.pose=copy.deepcopy(self.cp['pose'])
        self.geometry=InputGeometry(self.cp['board'],self.cp['local_size'],'windows_legacy_mouse_pixels')
        self.t=self.case['start_monotonic'];self._clock_at=time.monotonic()
        self.actions=[];self.releases=0;self.cancel=False;self.perturb_trial=False;self.perturbed=False
        self.perturb_after_action=2;self.cancel_after_action=False;self.unknown_completion=False
        self.trial_visual_timeout=False;self.trial_visual_timed_out=False
        self.interrupt_second_return=False;self.return_not_started=False
    def checkpoint(self,label,deadline):
        self.clock();self.check(deadline);self.t+=self.case['checkpoint_seconds'];self.check(deadline)
        cp=copy.deepcopy(self.cp);cp.update(label=label,pose=copy.deepcopy(self.pose),
            client_hex=score_native_pose(self.session,self.pose,self.case['rules'])['colors'])
        return cp
    def frames(self,label,deadline):
        self.clock();self.check(deadline);self.t+=self.case['visual_seconds'];self.check(deadline)
        if self.trial_visual_timeout and label=='refine_0_1_after' and not self.trial_visual_timed_out:
            self.trial_visual_timed_out=True;raise TimeoutError('simulated final trial visual timeout')
        colors=score_native_pose(self.session,self.pose,self.case['rules'])['colors']
        return [dict(hex=colors,remaining_seconds=None,timer_advisory=True,
            captured_monotonic=self.t+offset,scope='simulated_screenshot_read') for offset in (-.01,0.)]
    def perform_candidate(self,record,label,deadline):
        self.clock();self.check(deadline)
        if self.interrupt_second_return and label=='refinement_return_0_1':
            self.t+=self.case['input_overhead_seconds'];self.return_not_started=True
            raise InputNotStarted('simulated preparation ended before second return gesture')
        self.actions.append(copy.deepcopy(record))
        self.t+=record['input_seconds']+self.case['input_overhead_seconds'];self.check(deadline)
        self.pose=replay_native_route(self.pose,[record],self.geometry,self.settings,
            wheel_delta_per_step=1.,sample_policy='all_recorded_points')['final_pose']
        if self.perturb_trial and label.startswith('refine_') and len(self.actions)==self.perturb_after_action:
            drag=native_drag_gesture(self.geometry,self.settings,1,1).record()
            self.pose=replay_native_route(self.pose,[drag],self.geometry,self.settings,
                wheel_delta_per_step=1.,sample_policy='all_recorded_points')['final_pose'];self.perturbed=True
        if self.cancel_after_action:self.cancel=True
        return dict(completed=not self.unknown_completion,input_source='explicit_recorded_cpu_simulation',gesture=record,
            actual_trace=[dict(actual_client=list(p)) for p in record['points']])


class RecordedRefinementTests(unittest.TestCase):
    candidate=controller_fixture.ProtectedRefinementControllerTests.candidate
    plan=controller_fixture.ProtectedRefinementControllerTests.plan
    def setUp(self):
        self.io=RecordedIO();self.rules=self.io.case['rules'];self.recovery_calls=0
    def run_recorded(self,name,allowance=None,perturb=False,perturb_after_action=2):
        self.io.perturb_trial=perturb
        self.io.perturb_after_action=perturb_after_action
        deadline=self.io.case['engineering_deadline'] if allowance is None else self.io.t+allowance
        original=refinement.find_recovery
        def actual_recovery(*args,**kwargs):
            self.recovery_calls+=1;return original(*args,**kwargs)
        with patch('native_live.controller.find_recovery',actual_recovery):
            result=run_goal_loop(self.io,self.io.session,self.io.settings,self.rules,
                engineering_deadline=deadline,clock=self.io.clock,planner=self.plan)
        ARTIFACTS.mkdir(parents=True,exist_ok=True)
        artifact=dict(scope='offline recorded CPU simulation; no real game input, no live screenshot verification',
            source_checkpoint=str(FIXTURE/'recorded-checkpoint.json'),
            charged_checkpoint_seconds=self.io.case['checkpoint_seconds'],
            charged_visual_seconds=self.io.case['visual_seconds'],
            charged_input_overhead_seconds=self.io.case['input_overhead_seconds'],
            timing_basis=self.io.case.get('timing_basis'),
            real_cpu_time_charged=True,allowance_seconds=deadline-self.io.case['start_monotonic'],
            actual_simulated_end=self.io.t,recovery_solver_calls=self.recovery_calls,result=result)
        (ARTIFACTS/(name+'.json')).write_text(json.dumps(artifact,indent=2,default=str),encoding='utf-8')
        return result
    def test_recorded_final_refines_within_remaining_fifty_one_seconds(self):
        result=self.run_recorded('improvement')
        self.assertEqual(result['initial']['checkpoint']['client_hex'],['#050300','#010101','#040402'])
        self.assertAlmostEqual(result['initial_maximum'],1.58338,places=4)
        self.assertTrue(self.io.actions,result.get('refinement_stop'))
        self.assertLess(result['maximum'],result['initial_maximum'])
        self.assertTrue(result['best_current']);self.assertTrue(result['screenshot_verified'])
        self.assertLess(self.io.t,self.io.case['engineering_deadline']-8.)
        self.assertEqual(len(result['planning_rounds']),1)
    def test_late_twenty_second_allowance_preserves_recorded_anchor_without_input(self):
        result=self.run_recorded('low-allowance',allowance=20.)
        self.assertEqual(self.io.actions,[])
        self.assertEqual(result['actual_colors'],self.io.cp['client_hex'])
        self.assertTrue(result['verified']);self.assertTrue(result['best_current'])
        self.assertEqual(result.get('refinement_stop'),'insufficient_protected_time')
    def test_actual_perturbed_trial_recovers_from_actual_pose_with_real_solver(self):
        result=self.run_recorded('perturbed-return',perturb=True)
        self.assertTrue(self.io.perturbed,result.get('refinement_stop'))
        self.assertGreater(self.recovery_calls,0,'Prepared inverse route must be insufficient for a perturbed actual pose')
        self.assertTrue(result['best_current'],result.get('refinement_stop'))
        self.assertLessEqual(result['maximum'],result['initial_maximum'])
        self.assertTrue(result['verified']);self.assertTrue(result['screenshot_verified'])
        self.assertEqual(result['refinement_attempts'][0]['status'],'restored')
        self.assertLess(self.io.t,self.io.case['engineering_deadline']-8.)
    def test_actual_first_prefix_disturbance_recovers_without_finishing_trial(self):
        result=self.run_recorded('perturbed-first-prefix',perturb=True,perturb_after_action=1)
        self.assertTrue(self.io.perturbed,result.get('refinement_stop'))
        self.assertGreater(self.recovery_calls,0)
        purposes=[step['purpose'] for step in result['steps']]
        self.assertEqual(purposes.count('refine'),1)
        self.assertTrue(result['best_current']);self.assertTrue(result['verified'])
        self.assertTrue(result['screenshot_verified'])
        self.assertLessEqual(result['maximum'],result['initial_maximum'])
        self.assertEqual(result['refinement_attempts'][0]['status'],'restored')
        self.assertLess(self.io.t,self.io.case['engineering_deadline']-8.)
    def test_f9_after_first_trial_prevents_any_further_input(self):
        self.io.cancel_after_action=True
        result=self.run_recorded('f9-first-prefix')
        self.assertEqual(result['stop_reason'],'interrupted')
        self.assertEqual(len(self.io.actions),1)
        self.assertFalse(result['verified']);self.assertEqual(self.io.releases,1)
    def test_unknown_trial_completion_does_not_guess_inverse_input(self):
        self.io.unknown_completion=True
        result=self.run_recorded('unknown-completion')
        self.assertEqual(result['stop_reason'],'input_outcome_unknown')
        self.assertEqual(len(self.io.actions),1)
        self.assertFalse(result['verified']);self.assertEqual(self.io.releases,1)
    def test_return_interrupted_after_one_inverse_recovers_actual_prefix_pose(self):
        self.io.trial_visual_timeout=True;self.io.interrupt_second_return=True
        # Inject a fully re-audited recorded refinement to isolate the partial
        # return fault from a three-second wall-clock search admission race.
        # Discovery time/coverage remains exercised by separate recorded tests.
        from input_gestures import PointerGesture
        from native_input_route_search import _needed
        from native_live.compromise import observed_quality
        route=[PointerGesture('rotate',((963,678),(1146,678),(1146,679)),right=True,
                    requested_angle=.3,arc_start=1).record(),
               PointerGesture('rotate',((965,664),(1175,665),(1175,664)),right=True,
                    requested_angle=-.3,arc_start=1).record()]
        def prepared(context,cp,rules,**kw):
            pose=replay_native_route(cp['pose'],route,self.io.geometry,self.io.settings,
                wheel_delta_per_step=1.,sample_policy='all_recorded_points')['final_pose']
            row=dict(input_route=route,final_pose=pose,prediction=score_native_pose(self.io.session,pose,rules),
                needed=_needed(route,3.,.5),source='recorded_partial_return_fault_fixture')
            candidate=refinement._protect(context,cp,rules,row,observed_quality(cp['client_hex'],rules),lambda:None)
            self.assertIsNotNone(candidate)
            return candidate
        with patch('native_live.controller.find_refinement',prepared):
            result=self.run_recorded('interrupted-return-prefix')
        self.assertTrue(self.io.trial_visual_timed_out)
        self.assertTrue(self.io.return_not_started)
        self.assertGreater(self.recovery_calls,0)
        self.assertEqual(result['actual_colors'],self.io.cp['client_hex'])
        self.assertTrue(result['best_current']);self.assertTrue(result['verified'])
        self.assertTrue(result['screenshot_verified'])
        self.assertEqual(result['refinement_attempts'][0]['status'],'restored')
        self.assertLess(self.io.t,self.io.case['engineering_deadline']-8.)


if __name__=='__main__':unittest.main()
