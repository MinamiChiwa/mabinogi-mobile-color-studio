"""Integer wheel pairs can reach scales between adjacent one-way notches."""
from test_support import load_local_palette_session
import json
from pathlib import Path
import unittest
import numpy as np
from native_input_response import InputGeometry,InputSettings,replay_native_route
from native_periodic_route import compile_periodic_approach


class PeriodicScaleCompileTests(unittest.TestCase):
    def test_sub_notch_scale_has_complete_replayed_route(self):
        geometry=InputGeometry((100,100,800,800),(624,624),'windows_legacy_mouse_pixels')
        settings=InputSettings(.5,3.,0.,.1,.01)
        reference=dict(position=[0.,0.],scale=1.,rotation_degrees=0.)
        target=dict(reference,scale=.9992)
        result=compile_periodic_approach(target,reference,geometry,settings,
            [[215,400],[450,450],[680,400]],wheel_delta_per_step=1.,time_budget_seconds=2.)
        self.assertLess(result['final_marker_error'],.1)
        self.assertTrue(result['modelled_reached'])
        self.assertTrue(any(g['kind']=='wheel' and g['wheel_steps']>0 for g in result['input_route']))
        self.assertTrue(any(g['kind']=='wheel' and g['wheel_steps']<0 for g in result['input_route']))
        self.assertTrue(all(abs(g['wheel_steps'])<=32 for g in result['input_route']))
        replay=replay_native_route(reference,result['input_route'],geometry,settings,
            sample_policy='all_recorded_points',wheel_delta_per_step=1.)
        self.assertEqual(replay['final_pose'],result['final_pose'])

    def test_fine_scale_at_game_upper_limit_uses_unclipped_order(self):
        geometry=InputGeometry((100,100,800,800),(624,624),'windows_legacy_mouse_pixels')
        settings=InputSettings(.5,3.,0.,.1,.01)
        reference=dict(position=[0.,0.],scale=3.,rotation_degrees=0.)
        target=dict(reference,scale=3.*.9992)
        result=compile_periodic_approach(target,reference,geometry,settings,
            [[215,400],[450,450],[680,400]],wheel_delta_per_step=1.,time_budget_seconds=2.)
        self.assertLess(result['final_marker_error'],.1)
        wheels=[g for g in result['input_route'] if g['kind']=='wheel']
        self.assertTrue(wheels)
        self.assertLess(wheels[0]['wheel_steps'],0)

    def test_recorded_three_white_similar_targets_remain_reachable_in_bounded_plan(self):
        from native_palette_scoring import load_session,score_native_pose
        from native_palette_search import PoseGrid
        from native_live.same_session_dye_planner import bind_planning_context,plan_from_checkpoint
        root=Path(__file__).resolve().parents[2]
        folder=root/'outputs/native-integration/candidate-release-rc16/ColorStudio/data/sessions/20261010-235332-5fe7c98a'
        if not folder.is_dir():self.skipTest('Private original similarity capture not distributed')
        record=json.loads((folder/'native-result.json').read_text(encoding='utf-8'))
        checkpoint=record['initial']['checkpoint']
        session=load_local_palette_session(next(folder.glob('native-captures/*validation_capture')))
        geometry=InputGeometry(checkpoint['board'],checkpoint['local_size'],'windows_legacy_mouse_pixels')
        settings=InputSettings(**json.loads(checkpoint['binding'])[3])
        context=bind_planning_context(session,checkpoint,geometry,settings,wheel_delta_per_step=1.,
            calibration_evidence=dict(source='saved_original_session',viewport_origin=[0,0],
                viewport_scale=[1,1],backend_during_actions_synchronously_recorded=True))
        # A deterministic clock tests the candidate/per-stage work contract,
        # independently of unrelated parallel CPU load.
        frames=[dict(hex=checkpoint['client_hex'],remaining_seconds=None,captured_monotonic=99.9),
                dict(hex=checkpoint['client_hex'],remaining_seconds=None,captured_monotonic=100.)]
        plan=plan_from_checkpoint(context,checkpoint,frames,record['rules'],
            PoseGrid((-.04,.04),(-.02,.02),9,5,(.99,1.,1.01,.9999),(0.,)),
            now=100.,engineering_deadline=190.,time_budget_seconds=25.,clock=lambda:100.)
        self.assertIsNotNone(plan['candidate'])
        candidate=plan['candidate']
        replay=replay_native_route(checkpoint['pose'],candidate['input_route'],geometry,settings,
            sample_policy='all_recorded_points',wheel_delta_per_step=1.)
        prediction=score_native_pose(session,replay['final_pose'],record['rules'])
        self.assertTrue(prediction['predicted_accepted'])
        self.assertTrue(all(delta<=8. for delta in prediction['deltas']))
        self.assertLessEqual(len(candidate['input_route']),64)

    def test_recorded_similarity_route_finishes_with_measured_action_allowance(self):
        from test_native_live_controller import FixtureIO
        from native_palette_scoring import load_session
        from native_live.controller import run_goal_loop
        root=Path(__file__).resolve().parents[2]
        folder=root/'outputs/native-integration/candidate-release-rc16/ColorStudio/data/sessions/20261010-235332-5fe7c98a'
        if not folder.is_dir():self.skipTest('Private original similarity capture not distributed')
        record=json.loads((folder/'native-result.json').read_text(encoding='utf-8'))
        io=FixtureIO();io.cp=record['initial']['checkpoint'];io.pose=dict(io.cp['pose'])
        io.session=load_local_palette_session(next(folder.glob('native-captures/*validation_capture')))
        io.settings=InputSettings(**json.loads(io.cp['binding'])[3])
        io.geometry=InputGeometry(io.cp['board'],io.cp['local_size'],'windows_legacy_mouse_pixels')
        perform=io.perform_candidate
        def measured_cost(*args,**kwargs):
            receipt=perform(*args,**kwargs)
            # The failed session's input/native-read legs cost 2.1–2.5s.
            io.t+=2.4
            return receipt
        io.perform_candidate=measured_cost
        result=run_goal_loop(io,io.session,io.settings,record['rules'],
            engineering_deadline=90.,clock=io.clock)
        self.assertTrue(result['accepted'],result.get('error',result['stop_reason']))
        self.assertTrue(all(delta<=8. for delta in result['actual_deltas']))
        self.assertFalse(result['compromise_selected'])
        self.assertLess(result['elapsed_seconds'],82.)
        self.assertGreater(result['effective_deadline']-io.t,10.)


if __name__=='__main__':unittest.main()
