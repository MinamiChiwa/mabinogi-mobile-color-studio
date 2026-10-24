"""Full controller input checks against a separate logical-coordinate replay."""
import copy,hashlib,unittest
from native_input_response import InputGeometry,replay_native_route
from native_input_compile import native_drag_gesture
from native_input_route_search import _needed
from native_palette_scoring import score_native_pose
from native_live.controller import run_goal_loop
from native_live.same_session_dye_planner import audit_candidate_endpoint,_plan_fingerprint,_json
from test_native_live_controller import FixtureIO
from test_native_dpi_input import mapping


class NativeDpiControllerTests(unittest.TestCase):
    def test_all_physical_steps_match_independent_logical_replay_at_common_dpi_scales(self):
        for scale in (1.25,1.5,1.75,2.):
            with self.subTest(scale=scale):
                io=FixtureIO();native=io.geometry
                packet=mapping(scale,native_size=(1600,1200),native_board=native.board)
                io.cp.update(board=[v*scale for v in native.board],pixel_mapping=packet)
                io.geometry=InputGeometry(io.cp['board'],io.cp['local_size'],'windows_legacy_mouse_pixels',packet)
                route=[native_drag_gesture(io.geometry,io.settings,12,5).record()]
                def logical(record):
                    changed=copy.deepcopy(record)
                    changed['points']=[(packet['target_client_x_by_physical_x'][p[0]],
                        packet['target_client_y_by_physical_y'][p[1]]) for p in record['points']]
                    return changed
                expected=replay_native_route(io.pose,[logical(g) for g in route],native,io.settings,
                    sample_policy='all_recorded_points',wheel_delta_per_step=1.)['final_pose']
                neutral=[dict(enabled=True,exact=True,colors=['#000000'],tolerance=0.)]*3
                colors=score_native_pose(io.session,expected,neutral)['colors']
                rules=[dict(enabled=True,exact=True,colors=[c],tolerance=0.) for c in colors]
                self.assertNotEqual(colors,io.cp['client_hex'])
                def perform(record,label,deadline):
                    io.check(deadline);io.actions.append(copy.deepcopy(record));io.t+=.5
                    io.pose=replay_native_route(io.pose,[logical(record)],native,io.settings,
                        sample_policy='all_recorded_points',wheel_delta_per_step=1.)['final_pose']
                    return dict(completed=True,actual_trace=[dict(actual_client=list(p)) for p in record['points']],
                        input_source='independent_logical_replay_no_game_input')
                io.perform_candidate=perform
                def planner(context,cp,frames,received,grid,**kw):
                    endpoint=replay_native_route(cp['pose'],route,io.geometry,io.settings,
                        sample_policy='all_recorded_points',wheel_delta_per_step=1.)['final_pose']
                    row=audit_candidate_endpoint(context,cp,received,dict(input_route=route,final_pose=endpoint,
                        prediction=score_native_pose(io.session,endpoint,received),needed=_needed(route,3.,.5)))
                    plan=dict(schema=4,context_fingerprint=context['fingerprint'],reference_pose=cp['pose'],
                        reference_frame_monotonic=frames[-1]['captured_monotonic'],planned_at=io.clock(),
                        effective_deadline=kw['engineering_deadline'],candidate=row,approach_candidate=None,
                        compromise_candidate=None,reserve_seconds=10.,verification_margin_seconds=8.,
                        normalized_rules=received,rules_fingerprint=hashlib.sha256(_json(received).encode()).hexdigest(),
                        result_classification='predicted_exact',nearest_diagnostic=None,reachability_conclusion='not_established')
                    plan['plan_fingerprint']=_plan_fingerprint(plan);return plan
                result=run_goal_loop(io,io.session,io.settings,rules,engineering_deadline=90.,clock=io.clock,planner=planner)
                self.assertTrue(result['accepted'],result.get('error'))
                self.assertEqual(result['actual_colors'],colors)
                self.assertEqual(result['steps'][0]['expected_pose'],expected)
                self.assertEqual(result['steps'][0]['after']['pose'],expected)
                self.assertTrue(result['screenshot_verified'])
                self.assertFalse(result['steps'][0].get('model_response_warning'))


if __name__=='__main__':unittest.main()
