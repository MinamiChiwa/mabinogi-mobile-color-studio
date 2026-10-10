"""Actual rc10 rotation residuals must not abandon a validated dark route."""
from test_support import read_local_fixture_text
from test_support import load_local_palette_session
import copy,hashlib,json,unittest
from pathlib import Path
from test_native_live_controller import FixtureIO
from native_palette_scoring import load_session
from native_input_response import InputGeometry,InputSettings
from test_support import requires_native_case
from native_live.controller import run_goal_loop
from native_live.same_session_dye_planner import _plan_fingerprint,_json,audit_candidate_endpoint


class NativeRouteContinuationTests(unittest.TestCase):
    def recorded(self,index):
        folder=Path(__file__).parent/'fixtures/native_live'/('rc10_rotation_'+str(index))
        requires_native_case(folder)
        case=json.loads(read_local_fixture_text(folder/'case.json'));io=FixtureIO()
        io.cp=copy.deepcopy(case['initial']);io.pose=copy.deepcopy(io.cp['pose'])
        io.session=load_local_palette_session(folder/'palette');io.settings=InputSettings(**case['settings'])
        io.geometry=InputGeometry(io.cp['board'],io.cp['local_size'],'windows_legacy_mouse_pixels')
        # Charge saved IO overhead plus paced input; never send an input or sleep.
        io.clock=lambda:io.t
        original=io.perform_candidate;frames=io.frames;checkpoints=io.checkpoint
        io.visual_labels=[]
        def perform(record,*args):
            receipt=original(record,*args)
            io.t+=record['input_seconds']+.15
            if len(io.actions)==2:io.pose=copy.deepcopy(case['after_rotation']['pose'])
            return receipt
        def frame_read(label,deadline):
            io.visual_labels.append(label)
            io.t+=9. if label in ('initial','plan_0_revalidate') and index==1 else 2.5
            return frames(label,deadline)
        def checkpoint(label,deadline):
            io.t+=.65
            return checkpoints(label,deadline)
        io.perform_candidate=perform;io.frames=frame_read;io.checkpoint=checkpoint
        calls=[]
        def planner(context,cp,frames,rules,grid,**kwargs):
            calls.append(True)
            if len(calls)>1:
                io.t+=23.5
                raise RuntimeError('A harmless rotation residual caused another full search')
            io.t+=23.3
            row=audit_candidate_endpoint(context,cp,rules,case['selected'])
            plan=dict(schema=4,context_fingerprint=context['fingerprint'],reference_pose=cp['pose'],
                reference_frame_monotonic=frames[-1]['captured_monotonic'],planned_at=io.clock(),
                effective_deadline=kwargs['engineering_deadline'],candidate=None,approach_candidate=None,
                compromise_candidate=row,reserve_seconds=10.,verification_margin_seconds=8.,
                normalized_rules=rules,rules_fingerprint=hashlib.sha256(_json(rules).encode()).hexdigest(),
                result_classification='not_found_in_budget',nearest_diagnostic=None,
                reachability_conclusion='not_established',seed_mode='recorded_real_failure_route',
                stop_reason='no_supported_accepted_candidate')
            plan['plan_fingerprint']=_plan_fingerprint(plan)
            return plan
        return io,case,planner,calls

    def test_both_rc10_real_residuals_finish_without_global_research(self):
        for index in (1,2):
            with self.subTest(session=index):
                io,case,planner,calls=self.recorded(index)
                result=run_goal_loop(io,io.session,io.settings,case['rules'],
                    engineering_deadline=90.,clock=io.clock,planner=planner)
                self.assertEqual(result['stop_reason'],'compromise_observed',result.get('error'))
                self.assertEqual(len(calls),1)
                self.assertEqual(len(io.actions),len(case['selected']['input_route']))
                self.assertLessEqual(result['maximum'],1.50 if index==1 else 3.47)
                self.assertTrue(result['steps'][1]['remaining_route_audit']['continued'])
                self.assertEqual(result['steps'][2]['before']['pose'],case['after_rotation']['pose'])

    def test_native_pose_residual_does_not_request_an_extra_visual_pair(self):
        io,case,planner,calls=self.recorded(2)
        result=run_goal_loop(io,io.session,io.settings,case['rules'],
            engineering_deadline=90.,clock=io.clock,planner=planner)
        self.assertEqual(result['stop_reason'],'compromise_observed')
        self.assertNotIn('candidate_0_step_1_after',io.visual_labels)
        self.assertTrue(result['screenshot_verified'])


if __name__=='__main__':unittest.main()
