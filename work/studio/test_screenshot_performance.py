"""Lossless hot-path contracts, not machine-dependent timing assertions."""
import tempfile,threading,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np


class ScreenshotPerformanceTests(unittest.TestCase):
    def test_sparse_nonperiodic_fallback_does_not_allocate_dense_slot_pages(self):
        from screenshot_prediction import PeriodicColorField
        field=PeriodicColorField(2400,1)
        field.add(np.zeros((100,100,3),np.uint8),np.ones((1,100,100),bool),np.eye(3))
        memory=sum(page.data.nbytes+page.keys.nbytes+page.indices.nbytes+
            (0 if page.slots is None else page.slots.nbytes) for page in field.pages[0].values())
        self.assertLess(memory,10000*60)
        self.assertEqual(len(field.rows[0]),10000)
    def test_geometry_cache_reuses_immutable_masks_and_invalidates_changed_geometry(self):
        from atlas_masks import material_masks,board_texture_mask
        scene=SimpleNamespace(board=(0,0,120,120),markers=[(20,70),(60,50),(100,80)],cards=[])
        first=material_masks(scene);texture=board_texture_mask(scene)
        self.assertIs(first,material_masks(scene))
        self.assertIs(texture,board_texture_mask(scene))
        self.assertFalse(first.flags.writeable)
        scene.markers[1]=(60,55)
        self.assertIsNot(first,material_masks(scene))

    def test_incremental_field_preserves_old_whole_rgb_and_scale_ties(self):
        from screenshot_prediction import PeriodicColorField,FIELD_DTYPE
        rng=np.random.default_rng(27);period=17.3;field=PeriodicColorField(period,2)
        masks=rng.random((2,30,30))>.25;expected=[np.empty(0,FIELD_DTYPE) for _ in masks]
        for scale,offset in ((1.,0.),(1.,.11),(2.,.11),(.7,.31),(2.,.11)):
            image=rng.integers(0,256,(30,30,3),dtype=np.uint8)
            pose=np.diag([scale,scale,1.]);pose[:2,2]=offset
            field.add(image,masks,pose)
            inverse=np.linalg.inv(pose)
            for i,mask in enumerate(masks):
                y,x=np.where(mask);points=np.mod(np.column_stack((x,y))@inverse[:2,:2].T+inverse[:2,2],period)
                row=np.empty(len(x),FIELD_DTYPE);keys=np.floor(points*4).astype(np.int64)
                row['key']=keys[:,0]*int(np.ceil(period*4))+keys[:,1]
                row['point']=points;row['rgb']=image[y,x];row['scale']=scale
                merged=np.concatenate((expected[i],row));merged=merged[np.lexsort((-merged['scale'],merged['key']))]
                expected[i]=merged[np.r_[True,merged['key'][1:]!=merged['key'][:-1]]]
        for actual,wanted in zip(field.rows,expected):
            actual=actual[np.argsort(actual['key'])]
            np.testing.assert_array_equal(actual,wanted)

    def test_field_second_frame_never_sorts_historical_rows(self):
        from screenshot_prediction import PeriodicColorField
        field=PeriodicColorField(20,1);image=np.zeros((20,20,3),np.uint8);masks=np.ones((1,20,20),bool)
        field.add(image,masks,np.eye(3))
        with patch('numpy.lexsort',side_effect=AssertionError('Historical field sorting forbidden')):
            field.add(image,masks,np.eye(3))
        self.assertEqual(len(field.rows[0]),400)

    def test_png_enqueue_does_not_wait_for_encoding_and_queue_is_bounded(self):
        from screenshot_evidence import ScreenshotWriter
        entered=threading.Event();release=threading.Event()
        def slow_save(*args,**kwargs):entered.set();release.wait(2)
        with tempfile.TemporaryDirectory() as folder,patch('PIL.Image.Image.save',side_effect=slow_save):
            writer=ScreenshotWriter(Path(folder),capacity=2)
            try:
                writer.submit('first.png',np.zeros((8,8,3),np.uint8))
                self.assertTrue(entered.wait(1))
                for i in range(8):writer.submit(f'{i}.png',np.zeros((8,8,3),np.uint8))
                self.assertLessEqual(writer.pending,2)
                self.assertGreater(writer.dropped,0)
            finally:release.set();writer.close()
