import unittest
from input_gestures import drag_gesture,wheel_gesture,grouped_rotation_gesture
from native_input_response import InputGeometry,InputSettings,replay_native_route


class PeriodicRouteTests(unittest.TestCase):
    def setUp(self):
        self.geometry=InputGeometry((100,100,800,800),(624,624),'windows_legacy_mouse_pixels')
        self.settings=InputSettings(.5,3.,0.,.1,.01)
        self.reference=dict(position=[0.,0.],scale=1.,rotation_degrees=0.)

    def test_standard_large_drag_and_multistep_wheel_are_not_micro_filtered(self):
        from native_live.project_closed_loop_io import validate_research_gesture
        for gesture in (drag_gesture(self.geometry.board,150,40),
                        wheel_gesture(self.geometry.board,-29),
                        grouped_rotation_gesture((132,132,768,768),4.)):
            accepted=validate_research_gesture(gesture.record(),self.geometry.board)
            self.assertEqual(accepted.record(),gesture.record())

    def test_large_translation_compiles_to_a_replayed_approach(self):
        from native_periodic_route import compile_periodic_approach
        target=dict(self.reference,position=[.17,-.22],scale=.75)
        result=compile_periodic_approach(target,self.reference,self.geometry,self.settings,
            [[215,400],[450,450],[680,400]],wheel_delta_per_step=1.,time_budget_seconds=2.)
        self.assertTrue(result['input_route'])
        self.assertLess(result['final_marker_error'],result['initial_marker_error'])
        replay=replay_native_route(self.reference,result['input_route'],self.geometry,self.settings,
            sample_policy='all_recorded_points',wheel_delta_per_step=1.)
        self.assertEqual(replay['final_pose'],result['final_pose'])
        self.assertFalse(result['execution_verified'])

    def test_pointer_outside_bound_game_board_is_rejected(self):
        from native_live.project_closed_loop_io import validate_research_gesture
        bad=wheel_gesture((0,0,1000,1000),1,anchor=(10,10)).record()
        with self.assertRaises(ValueError):validate_research_gesture(bad,self.geometry.board)


if __name__=='__main__':unittest.main()
