import unittest
import numpy as np
import cv2
from unittest.mock import patch
from vision import measure_board_motion
from analyze_live_atlas import measured_translation, measure_periods, validation_summary, quality_gate


class RegistrationTests(unittest.TestCase):
    def test_cached_features_preserve_measured_motion_and_are_scoped_to_board(self):
        rng=np.random.default_rng(918)
        before=rng.integers(0,256,(240,360,3),dtype=np.uint8)
        before=cv2.GaussianBlur(before,(3,3),0)
        after=np.roll(before,(7,11),axis=(0,1));board=(0,0,360,240)
        baseline=measure_board_motion(before,after,board)
        cache={};detector=cv2.SIFT_create(nfeatures=1800)
        from unittest.mock import MagicMock
        wrapped=MagicMock(wraps=detector)
        with patch('vision.cv2.SIFT_create',return_value=wrapped):
            first=measure_board_motion(before,after,board,feature_cache=cache)
            second=measure_board_motion(before,after,board,feature_cache=cache)
            self.assertEqual(wrapped.detectAndCompute.call_count,2)
            measure_board_motion(before,after,(10,10,350,230),feature_cache=cache)
            self.assertEqual(wrapped.detectAndCompute.call_count,4)
        self.assertIsNotNone(baseline)
        np.testing.assert_allclose(first['matrix'],baseline['matrix'])
        self.assertEqual(first,second)

    def test_period_measurement_obeys_cancellation_before_matching(self):
        image=np.zeros((240,360,3),np.uint8)
        def cancelled():raise RuntimeError('cancelled')
        with self.assertRaisesRegex(RuntimeError,'cancelled'):
            measure_periods([image]*3,[[0,0],[240,0],[0,240]],
                            np.ones((3,240,360),bool),check=cancelled)

    def test_bad_earlier_holdout_cannot_be_hidden_by_good_final_frame(self):
        coverage=[dict(region=i,coverage=1.) for i in (1,2,3)]
        frames=[dict(prediction=[dict(region=i,coverage=1.,rgb_rmse=rmse)
                                 for i in (1,2,3)]) for rmse in (15.,2.)]
        self.assertFalse(quality_gate(coverage,validation_summary(frames))['passed'])
        frames[0]['prediction'][0]['rgb_rmse']=None
        self.assertFalse(quality_gate(coverage,validation_summary(frames))['passed'])

    def test_period_larger_than_viewport_from_independent_axis_returns(self):
        rng=np.random.default_rng(413)
        tile=rng.integers(0,256,(300,300,3),dtype=np.uint8)
        tile=cv2.GaussianBlur(tile,(3,3),0)
        y,x=np.mgrid[:240,:360]
        offsets=np.array([[0,0],[240,0],[280,0],[0,240],[0,280]])
        images=[tile[(y-dy)%300,(x-dx)%300] for dx,dy in offsets]
        masks=np.array([(x>=lo)&(x<lo+120) for lo in (0,120,240)])
        (px,ex),(py,ey)=measure_periods(images,offsets,masks)
        self.assertAlmostEqual(px,300,delta=.3)
        self.assertAlmostEqual(py,300,delta=.3)
        self.assertLess(max(ex,ey),8)

    def test_textureless_frames_do_not_invent_a_period(self):
        image=np.zeros((240,360,3),np.uint8)
        with self.assertRaises(ValueError):measured_translation(image,image)
        with self.assertRaisesRegex(ValueError,'Insufficient'):
            measure_periods([image]*3,[[0,0],[240,0],[0,240]],
                            np.ones((3,240,360),bool))


if __name__=='__main__':unittest.main()
