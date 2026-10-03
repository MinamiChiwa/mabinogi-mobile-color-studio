import unittest
import numpy as np
import cv2
import json
from pathlib import Path
from PIL import Image
from unittest.mock import patch
from vision import measure_board_motion
from analyze_live_atlas import measured_translation, measure_periods, validation_summary, quality_gate


class RegistrationTests(unittest.TestCase):
    def low_contrast(self):
        rng=np.random.default_rng(7321)
        image=cv2.GaussianBlur(rng.integers(0,256,(240,360,3),dtype=np.uint8),(3,3),0)
        return np.rint(128+(image.astype(float)-128)*.12).clip(0,255).astype(np.uint8)

    def test_low_contrast_retry_uses_more_features_with_same_inlier_gates(self):
        before=self.low_contrast();after=np.roll(before,(7,11),axis=(0,1))
        cache={};diagnostics={}
        self.assertIsNone(measure_board_motion(before,after,(0,0,360,240),feature_cache=cache))
        shift=measured_translation(before,after,feature_cache=cache,diagnostics=diagnostics)
        np.testing.assert_allclose(shift,[11,7],atol=.01)
        self.assertEqual(diagnostics['method'],'dense_sift_retry')
        self.assertGreaterEqual(diagnostics['attempts'][-1]['inliers'],20)
        self.assertGreaterEqual(diagnostics['attempts'][-1]['inlier_ratio'],.5)
        self.assertEqual(len(cache),4)  # Two frames, two detector settings.
        repeated=measured_translation(before,after,feature_cache=cache)
        np.testing.assert_allclose(repeated,shift)

    def test_dense_features_do_not_turn_rotation_into_translation(self):
        before=self.low_contrast()
        after=cv2.warpAffine(before,cv2.getRotationMatrix2D((180,120),3,1),(360,240))
        diagnostics={}
        with self.assertRaisesRegex(ValueError,'Texture translation'):
            measured_translation(before,after,diagnostics=diagnostics)
        self.assertEqual(diagnostics['reason'],'non_translation_motion')

    def test_newest_saved_sparse_pair_recovers_without_lowering_match_threshold(self):
        from analyze_live_atlas import scene_record
        from atlas_masks import material_masks
        folder=Path(__file__).parent/'data/sessions/20260929-235056-18437c3a/atlas_capture'
        if not (folder/'grid_011_board.png').exists():self.skipTest('Local game capture unavailable')
        scene=scene_record(json.loads((folder/'log.json').read_text(encoding='utf-8')))
        masks=material_masks(scene);texture=masks.any(axis=0)
        images=[]
        for name in ('grid_010','grid_011'):
            with Image.open(folder/(name+'_board.png')) as image:images.append(np.array(image.convert('RGB')))
        height,width=images[0].shape[:2];baseline={};recovered={}
        self.assertIsNone(measure_board_motion(*images,(0,0,width,height),
                                              texture_mask=texture,diagnostics=baseline))
        self.assertEqual(baseline['reason'],'insufficient_inliers')
        shift=measured_translation(*images,texture_mask=texture,diagnostics=recovered)
        self.assertEqual(recovered['method'],'dense_sift_retry')
        np.testing.assert_allclose(shift,[50,0],atol=.2)
        self.assertGreaterEqual(recovered['attempts'][-1]['inliers'],20)

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

    def test_single_validated_return_is_used_as_a_degraded_period(self):
        rng=np.random.default_rng(414)
        tile=rng.integers(0,256,(300,300,3),dtype=np.uint8)
        tile=cv2.GaussianBlur(tile,(3,3),0)
        y,x=np.mgrid[:240,:360]
        offsets=np.array([[0,0],[240,0],[280,0],[0,240]])
        images=[tile[(y-dy)%300,(x-dx)%300] for dx,dy in offsets]
        masks=np.array([(x>=lo)&(x<lo+120) for lo in (0,120,240)])
        # Remove the second vertical return: the remaining independent return
        # still provides a bounded period and later quality validation decides
        # whether the atlas is safe to publish.
        (px,ex),(py,ey)=measure_periods(images,offsets,masks)
        self.assertAlmostEqual(px,300,delta=.3)
        self.assertAlmostEqual(py,300,delta=.3)


if __name__=='__main__':unittest.main()
