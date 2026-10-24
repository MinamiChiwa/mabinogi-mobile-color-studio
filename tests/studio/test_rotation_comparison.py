import unittest
import numpy as np
from input_gestures import rotation_gesture,planned_gesture
from rotation_comparison import grouped_rotation_gesture
from gesture_response_probe import rotation_comparison_plan
from rotation_probe_review import angular_increments,incremental_prediction,fit_increment_hypothesis


class RotationComparisonTests(unittest.TestCase):
    def test_grouping_preserves_pivot_radial_path_endpoint_and_timing(self):
        for board in ((0,0,498,498),(1125,259,1826,960),(-900,-800,1500,1600)):
            l,t,r,b=board
            for anchor in (((l+r)/2,(t+b)/2),(l+(r-l)*.22,t+(b-t)*.72)):
                for angle in (-12,-5,-.4,-.01,.01,.4,5,12):
                    original=rotation_gesture(board,angle,anchor)
                    grouped=grouped_rotation_gesture(board,angle,anchor)
                    self.assertEqual(original.points[:9],grouped.points[:9])
                    self.assertEqual(original.points[-1],grouped.points[-1])
                    self.assertEqual(original.timing,grouped.timing)
                    self.assertEqual(original.duration,grouped.duration)
                    self.assertEqual(len(original.points),len(grouped.points))
                    self.assertEqual(original.has_effect,grouped.has_effect)
                    self.assertTrue(set(grouped.points).issubset(original.points))
                    self.assertTrue(all(type(v)is int for p in grouped.points for v in p))

    def test_small_arc_groups_motion_but_does_not_invent_a_subpixel_endpoint(self):
        board=(1125,259,1826,960);anchor=(1476,610)
        original=rotation_gesture(board,.4,anchor)
        grouped=grouped_rotation_gesture(board,.4,anchor)
        self.assertGreater(len(set(original.points[8:])),2)
        self.assertEqual(len(set(grouped.points[8:])),2)
        self.assertAlmostEqual(original.arc_degrees,grouped.arc_degrees,places=10)
        # This model is a diagnostic hypothesis, not a game success test.
        self.assertEqual(incremental_prediction(original.record(),.114),0.)
        self.assertGreater(incremental_prediction(grouped.record(),.114),.3)
        self.assertFalse(grouped_rotation_gesture(board,.001,anchor).has_effect)

    def test_production_uses_grouped_arc_and_baseline_remains_available(self):
        board=(1125,259,1826,960)
        self.assertEqual(planned_gesture('rotate',board,.4),grouped_rotation_gesture(board,.4))
        self.assertEqual(rotation_gesture(board,12),grouped_rotation_gesture(board,12))
        self.assertNotEqual(rotation_gesture(board,.4),grouped_rotation_gesture(board,.4))

    def test_counterbalanced_pairs_cover_both_pivots_and_directions(self):
        plan=rotation_comparison_plan((1125,259,1826,960))
        self.assertEqual(len(plan),32)
        for index in range(0,32,2):
            first,second=plan[index:index+2]
            self.assertEqual(first.repeat,second.repeat)
            self.assertEqual(first.anchor_name,second.anchor_name)
            self.assertEqual(first.gesture.requested_angle,second.gesture.requested_angle)
            self.assertEqual(first.gesture.points[-1],second.gesture.points[-1])
            self.assertEqual((first.variant,second.variant),
                             ('legacy','grouped') if first.repeat==0 else ('grouped','legacy'))

    def test_hypothesis_fits_first_repeat_only_and_marks_it_uninstalled(self):
        def sample(repeat,step,actual):
            gesture=rotation_gesture((1125,259,1826,960),.4).record()
            return dict(gesture=gesture,repeat=repeat,step=step,registration_complete=True,
                        response={'angle':actual})
        training=sample(0,1,0.)
        result=fit_increment_hypothesis([training,sample(1,2,10.)])
        self.assertEqual(result['training_steps'],[1])
        self.assertEqual(result['repeat_steps'],[2])
        self.assertGreater(result['within_session_repeat']['maximum'],9)
        self.assertFalse(result['response_model_installed'])
        self.assertFalse(fit_increment_hypothesis([])['available'])

    def test_invalid_arc_does_not_produce_a_prediction(self):
        with self.assertRaises(ValueError):
            angular_increments(dict(points=[[0,0],[0,0]],arc_start=0))


if __name__=='__main__':unittest.main()
