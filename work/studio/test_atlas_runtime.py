import unittest
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import cv2
import numpy as np
from PIL import Image
import atlas_runtime
from atlas_runtime import motion, Adapter


class RuntimeMotionTests(unittest.TestCase):
    def test_large_point_cloud_is_remapped_in_bounded_chunks(self):
        source=np.arange(12*13*3,dtype=np.float32).reshape(12,13,3)
        px=np.resize(np.linspace(0.25,11.5,12,dtype=np.float32),40001)
        py=np.resize(np.linspace(0.75,10.5,12,dtype=np.float32),40001)
        original=atlas_runtime.cv2.remap
        calls=[]
        def wrapped(image,xmap,ymap,interpolation):
            calls.append((xmap.shape,ymap.shape))
            return original(image,xmap,ymap,interpolation)
        with patch.object(atlas_runtime.cv2,'remap',side_effect=wrapped):
            result=atlas_runtime._remap_points(source,px,py)
        self.assertEqual(result.shape,(40001,3))
        self.assertEqual(len(calls),3)
        self.assertLessEqual(max(shape[0] for shape,_ in calls),16384)
        self.assertEqual(calls[-1][0][0],7233)

    def scene(self):
        return SimpleNamespace(board=(0,0,498,498),
                               markers=[(83,200),(249,300),(415,100)],cards=[])

    def frames(self, delta):
        rng=np.random.default_rng(51)
        tile=cv2.GaussianBlur(rng.integers(0,145,(640,640,3),dtype=np.uint8),(3,3),0)
        y,x=np.mgrid[:498,:498]
        tint=np.array([[90,0,0],[0,90,0],[0,0,90]],np.uint8)[x//166]
        a=tile[y,x]+tint
        b=tile[(y-delta[1])%640,(x-delta[0])%640]+tint
        return a,b

    def test_cross_material_motion_uses_same_material_rgb_only(self):
        for delta in ((50,0),(-48,0),(25,75)):
            a,b=self.frames(delta)
            measured=motion(a,b,self.scene())
            self.assertIsNotNone(measured)
            np.testing.assert_allclose(np.array(measured['matrix'])[:,2],delta,atol=.15)
            self.assertLess(max(measured['region_rgb_rmse']),2)

    def test_geometry_match_cannot_hide_a_material_color_change(self):
        a,b=self.frames((50,0))
        b=b.copy(); b[:,166:332]=np.clip(b[:,166:332].astype(int)+30,0,255).astype(np.uint8)
        self.assertIsNone(motion(a,b,self.scene()))

    def test_untextured_frames_still_fail_with_diagnostics(self):
        a=np.zeros((498,498,3),np.uint8);diagnostics={}
        self.assertIsNone(motion(a,a,self.scene(),diagnostics))
        self.assertFalse(diagnostics['passed'])
        self.assertEqual(diagnostics['reason'],'insufficient_features')

    def test_adapter_retains_exact_pair_without_extra_capture_or_input(self):
        a,b=self.frames((25,75))
        adapter=Adapter(object(),self.scene(),'offline')
        self.assertIsNotNone(adapter.motion(a,b))
        self.assertIs(adapter.last_motion_before,a)
        self.assertIs(adapter.last_motion_after,b)
        self.assertTrue(adapter.last_motion_diagnostics['passed'])

    def test_rotation_and_zoom_with_fixed_material_boundaries(self):
        scene=self.scene();a,_=self.frames((0,0))
        y,x=np.mgrid[:498,:498]
        tint=np.array([[90,0,0],[0,90,0],[0,0,90]],np.uint8)[x//166]
        texture=a-tint
        for angle,scale in ((12,1),(-8,.99)):
            matrix=cv2.getRotationMatrix2D((249,249),angle,scale)
            b=cv2.warpAffine(texture,matrix,(498,498),borderMode=cv2.BORDER_WRAP)+tint
            measured=motion(a,b,scene)
            self.assertIsNotNone(measured)
            np.testing.assert_allclose(measured['matrix'],matrix,atol=.2)


class ArchivedExecutionMotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder=Path(__file__).parent/'data/sessions/20260927-103442/atlas_capture'
        if not (folder/'execution/attempt-01.png').is_file():
            raise unittest.SkipTest('Real execution failure archive is unavailable')
        log=json.loads((folder/'log.json').read_text(encoding='utf-8'))
        cls.scene=SimpleNamespace(**next(e for e in log if e['kind']=='sampling_ready'))
        cls.before=np.array(Image.open(folder/'grid_048.png').convert('RGB'))
        cls.after=np.array(Image.open(folder/'execution/attempt-01.png').convert('RGB'))

    def test_sparse_real_drag_retries_existing_frames_and_keeps_quality_gates(self):
        diagnostics={}
        measured=motion(self.before,self.after,self.scene,diagnostics)
        self.assertIsNotNone(measured)
        self.assertEqual(diagnostics['attempts'][0]['reason'],'insufficient_inliers')
        self.assertLess(diagnostics['attempts'][0]['inliers'],40)
        self.assertGreaterEqual(measured['inliers'],40)
        np.testing.assert_allclose(np.array(measured['matrix'])[:,2],[-49,80],atol=.15)
        self.assertLess(max(measured['region_rgb_rmse']),10)
        reverse=motion(self.after,self.before,self.scene)
        self.assertIsNotNone(reverse)
        forward_matrix=np.vstack((measured['matrix'],[0,0,1]))
        reverse_matrix=np.vstack((reverse['matrix'],[0,0,1]))
        np.testing.assert_allclose(reverse_matrix@forward_matrix,np.eye(3),atol=.15)

    def test_denser_features_cannot_accept_real_material_color_change(self):
        after=self.after.copy();l,t,r,b=self.scene.board
        region=after[t:b,l+166:l+332]
        region[:]=np.clip(region.astype(int)+30,0,255).astype(np.uint8)
        diagnostics={}
        self.assertIsNone(motion(self.before,after,self.scene,diagnostics))
        self.assertEqual(diagnostics['reason'],'material_rgb_mismatch')
        self.assertGreater(diagnostics['region_rgb_rmse'][1],10)


if __name__=='__main__':unittest.main()
