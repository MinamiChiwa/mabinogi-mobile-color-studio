"""Recorded rc12 user trials, replayed offline through protected refinement."""
from test_support import read_local_fixture_text
from test_support import load_local_palette_session
import copy,json,time,unittest
from pathlib import Path
from unittest.mock import patch
import test_native_refinement_recorded as recorded_fixture
import test_native_refinement_controller as controller_fixture
from native_input_response import InputGeometry,InputSettings
from native_palette_scoring import load_session,score_native_pose
from native_live.controller import run_goal_loop
from native_live import refinement

ROOT=Path(__file__).parent
ARTIFACTS=ROOT.resolve().parents[1]/'outputs/native-integration/verification/rc13-user-tests/recorded'
NEUTRAL=[dict(enabled=True,exact=True,colors=['#000000'],tolerance=0.) for _ in range(3)]


class UserRecordedIO(recorded_fixture.RecordedIO):
    def __init__(self,kind):
        super().__init__()
        self.fixture=ROOT/('fixtures/native_live/rc12_refinement_'+kind)
        self.case=json.loads(read_local_fixture_text(self.fixture/'case.json', encoding='utf-8'))
        self.cp=copy.deepcopy(self.case['initial']);self.session=load_local_palette_session(self.fixture/'palette')
        self.settings=InputSettings(**self.case['settings']);self.pose=copy.deepcopy(self.cp['pose'])
        self.geometry=InputGeometry(self.cp['board'],self.cp['local_size'],'windows_legacy_mouse_pixels')
        self.t=self.case['start_monotonic'];self._clock_at=time.monotonic()
    def checkpoint(self,label,deadline):
        self.clock();self.check(deadline);self.t+=self.case['checkpoint_seconds'];self.check(deadline)
        return dict(copy.deepcopy(self.cp),label=label,pose=copy.deepcopy(self.pose),
            client_hex=score_native_pose(self.session,self.pose,NEUTRAL)['colors'])
    def frames(self,label,deadline):
        self.clock();self.check(deadline);self.t+=self.case['visual_seconds'];self.check(deadline)
        codes=score_native_pose(self.session,self.pose,NEUTRAL)['colors']
        return [dict(hex=codes,remaining_seconds=None,timer_advisory=True,
            captured_monotonic=self.t+offset,scope='simulated_visual_pair') for offset in (-.01,0.)]


class Rc12UserRefinementTests(unittest.TestCase):
    candidate=controller_fixture.ProtectedRefinementControllerTests.candidate
    plan=controller_fixture.ProtectedRefinementControllerTests.plan
    def prepare(self,kind):
        self.io=UserRecordedIO(kind);self.rules=self.io.case['rules'];self.search_calls=[];self.recovery_calls=0
    def run_case(self,name,deadline=None,perturb=False):
        self.io.perturb_trial=perturb
        until=self.io.case['engineering_deadline'] if deadline is None else deadline
        original_search=refinement.find_refinement;original_recovery=refinement.find_recovery
        def search(*args,**kwargs):
            at=self.io.clock();row=original_search(*args,**kwargs)
            self.search_calls.append(dict(started=at,phase_deadline=kwargs['deadline'],
                allowance=kwargs['deadline']-at,diagnostics=copy.deepcopy(kwargs.get('stats')),
                published=bool(row)));return row
        def recovery(*args,**kwargs):
            self.recovery_calls+=1;return original_recovery(*args,**kwargs)
        with patch('native_live.controller.find_refinement',search),patch('native_live.controller.find_recovery',recovery):
            result=run_goal_loop(self.io,self.io.session,self.io.settings,self.rules,
                engineering_deadline=until,clock=self.io.clock,planner=self.plan)
        ARTIFACTS.mkdir(parents=True,exist_ok=True)
        artifact=dict(scope='Offline CPU replay of rc12 recorded final colors and poses; no game input or live visual verification',
            source_fixture=str(self.io.fixture),actual_inputs_sent=0,
            simulated_physical_gestures=len(self.io.actions),
            extra_simulated_initial_visual_seconds=getattr(self.io,'extra_initial_visual_seconds',0.),
            supplied_deadline=until,actual_simulated_end=self.io.t,search_calls=self.search_calls,
            recovery_calls=self.recovery_calls,timing_basis=self.io.case['timing_basis'],
            charged_native_seconds=.7,charged_frame_seconds=1.5,charged_input_overhead_seconds=.2,
            result=result)
        (ARTIFACTS/(name+'.json')).write_text(json.dumps(artifact,indent=2,default=str),encoding='utf-8')
        return result
    def test_double_receives_ten_second_search_opportunity_and_improves(self):
        self.prepare('double');result=self.run_case('double-new-cap')
        self.assertTrue(self.search_calls,result.get('refinement_stop'))
        self.assertGreaterEqual(self.search_calls[0]['allowance'],9.)
        self.assertTrue(self.io.actions,result.get('refinement_stop'))
        self.assertLess(result['maximum'],result['initial_maximum'])
        self.assertTrue(result['best_current']);self.assertTrue(result['screenshot_verified'])
        self.assertLess(self.io.t,self.io.case['engineering_deadline']-8.)
    def test_triple_generic_expanded_search_finds_exact_black(self):
        self.prepare('triple');result=self.run_case('triple-new-cap')
        self.assertTrue(result['accepted'],result.get('refinement_stop'))
        self.assertEqual(result['actual_colors'],['#000000']*3)
        self.assertTrue(result['screenshot_verified']);self.assertTrue(result['best_current'])
        self.assertLess(self.io.t,self.io.case['engineering_deadline']-8.)
        stats=result['refinement_searches'][0]
        self.assertGreater(stats['checked_routes'],0)
        self.assertLessEqual(stats['checked_routes'],stats['finite_candidate_upper_bound'])
        self.assertGreater(stats['audited_candidates'],0)
        self.assertGreaterEqual(stats['return_checked'],2)
        self.assertTrue(stats['protected_candidate_found'])
        self.assertIs(type(stats['family_exhausted']),bool)
        self.assertIs(type(stats['deadline_reached']),bool)
    def test_twenty_second_allowance_keeps_double_anchor_without_input(self):
        self.prepare('double');result=self.run_case('double-twenty-second',deadline=self.io.t+20.)
        self.assertEqual(self.io.actions,[])
        self.assertEqual(result['actual_colors'],self.io.cp['client_hex'])
        self.assertTrue(result['verified']);self.assertTrue(result['best_current'])
        self.assertEqual(result.get('refinement_stop'),'insufficient_protected_time')
    def test_supplied_original_engineering_cap_is_never_extended(self):
        self.prepare('double');old=self.io.case['original_engineering_deadline']
        result=self.run_case('double-old-cap',deadline=old)
        self.assertLessEqual(result['effective_deadline'],old)
        self.assertLess(self.io.t,old)
        self.assertTrue(result['verified']);self.assertTrue(result['best_current'])
    def test_double_actual_perturbation_restores_anchor_before_reserved_deadline(self):
        self.prepare('double');result=self.run_case('double-perturbed-return',perturb=True)
        self.assertTrue(self.io.perturbed,result.get('refinement_stop'))
        self.assertGreater(self.recovery_calls,0)
        self.assertTrue(result['verified']);self.assertTrue(result['best_current'])
        self.assertLessEqual(result['maximum'],result['initial_maximum'])
        self.assertTrue(result['screenshot_verified'])
        self.assertEqual(result['refinement_attempts'][0]['status'],'restored')
        self.assertLess(self.io.t,self.io.case['engineering_deadline']-8.)
    def test_cold_initial_visual_cost_does_not_block_warm_refinement(self):
        self.prepare('double');original=self.io.frames
        self.io.extra_initial_visual_seconds=3.
        def cold(label,deadline):
            if label=='initial':self.io.t+=3.
            return original(label,deadline)
        self.io.frames=cold;result=self.run_case('double-cold-initial')
        self.assertTrue(self.io.actions,result.get('refinement_stop'))
        self.assertLess(result['maximum'],result['initial_maximum'])
        self.assertTrue(result['verified']);self.assertTrue(result['best_current'])
        self.assertLess(self.io.t,self.io.case['engineering_deadline']-8.)


if __name__=='__main__':unittest.main()
