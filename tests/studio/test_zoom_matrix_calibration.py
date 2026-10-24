import unittest
import numpy as np
from live_atlas_capture import summarize_zoom_calibration


class ZoomMatrixCalibrationTests(unittest.TestCase):
    def measurements(self):
        return [dict(steps=-1,motion=dict(scale=.9902,angle=0.,
                    matrix=[[.9902098940128454,0.,-2.1456789],
                            [0.,.9902098940128454,3.9876543]])),
                dict(steps=1,motion=dict(scale=1.0097,angle=0.,
                    matrix=[[1.0096693733007436,0.,2.3345678],
                            [0.,1.0096693733007436,-4.1234567]]))]

    def test_detent_spacing_and_net_pose_use_full_measured_matrix(self):
        observations=self.measurements()
        result=summarize_zoom_calibration(observations,current_scale=1.2)
        self.assertTrue(result['passed'])
        self.assertEqual(result['scale_source'],'measured_affine_matrix')
        self.assertAlmostEqual(result['down_log_step'],
            abs(np.log(observations[0]['motion']['matrix'][0][0])),places=14)
        self.assertAlmostEqual(result['up_log_step'],
            abs(np.log(observations[1]['motion']['matrix'][0][0])),places=14)
        self.assertNotAlmostEqual(result['down_log_step'],abs(np.log(.9902)),places=7)
        down=np.vstack((observations[0]['motion']['matrix'],[0,0,1]))
        up=np.vstack((observations[1]['motion']['matrix'],[0,0,1]))
        np.testing.assert_array_equal(result['net_matrix'],(up@down)[:2])
        self.assertEqual(result['measurements'],observations)
        self.assertAlmostEqual(result['current_scale'],1.2*np.hypot((up@down)[0,0],(up@down)[1,0]))

    def test_rounded_summary_cannot_override_wrong_direction_or_rotation(self):
        for matrix in ([[1.01,0,0],[0,1.01,0]],
                       [[.9902,-.01,0],[.01,.9902,0]]):
            observations=self.measurements()
            observations[0]['motion']['matrix']=matrix
            result=summarize_zoom_calibration(observations)
            self.assertFalse(result['passed'])
            self.assertIsNone(result['down_log_step'])

    def test_missing_nonfinite_and_nonsimilarity_matrix_are_rejected(self):
        for matrix in (None,[[.99,0],[0,.99]],[[np.nan,0,0],[0,.99,0]],
                       [[.99,.001,0],[0,.99,0]]):
            observations=self.measurements()
            observations[0]['motion']['matrix']=matrix
            result=summarize_zoom_calibration(observations)
            self.assertFalse(result['passed'])
            self.assertIsNone(result['current_scale'])


if __name__=='__main__':unittest.main()
