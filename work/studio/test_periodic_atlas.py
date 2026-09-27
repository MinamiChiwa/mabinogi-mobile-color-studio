import unittest
import json
import tempfile
from pathlib import Path
import numpy as np
from PIL import Image
from atlas_review import review
from analyze_live_atlas import quality_gate, frame_sequence, scene_record
from periodic_atlas import PeriodicAtlas, translation_candidates


class AtlasTests(unittest.TestCase):
    def test_scene_record_prefers_sampling_geometry(self):
        log=[dict(kind='ready',board=(1,1,2,2)),
             dict(kind='sampling_ready',board=(3,3,4,4))]
        self.assertEqual(scene_record(log)['board'],(3,3,4,4))

    def test_frame_sequence_supports_grid_holdouts(self):
        log=[dict(kind='frame',name='max_sampling'),
             dict(kind='frame',name='grid_001'),dict(kind='command',holdout=False),
             dict(kind='frame',name='grid_002'),dict(kind='command',holdout=True)]
        result=frame_sequence(log)
        self.assertEqual(result['strategy'],'grid')
        self.assertEqual(result['names'],['max_sampling','grid_001','grid_002'])
        self.assertEqual(result['holdout_indices'],[2])

    def test_quality_gate_rejects_sparse_or_unvalidated_atlas(self):
        coverage=[dict(region=i+1,coverage=.95) for i in range(3)]
        validation=[dict(coverage=.93,rgb_rmse=3.0) for _ in range(3)]
        self.assertTrue(quality_gate(coverage,validation)['passed'])
        validation[1]['rgb_rmse']=8.01
        self.assertFalse(quality_gate(coverage,validation)['passed'])
        coverage[2]['coverage']=.89
        self.assertFalse(quality_gate(coverage,validation)['passed'])
    def setUp(self):
        self.tile = np.random.default_rng(21).integers(0, 256, (8, 8, 3), dtype=np.uint8)
        self.masks = np.ones((3, 8, 8), bool)
        self.rules = [dict(enabled=True, colors=['#000000'], exact=True, tolerance=4) for _ in range(3)]

    def test_wrapped_measured_motion_reconstructs_missing_pixels(self):
        atlas = PeriodicAtlas([[8, 0], [0, 8]], resolution=8)
        masks = self.masks.copy(); masks[:, :, 4:] = False
        atlas.add(self.tile, masks)
        shifted = np.roll(self.tile, 4, axis=1)
        atlas.add(shifted, masks, (4, 0))
        colors, valid, _ = atlas.maps()
        self.assertTrue(valid.all())
        np.testing.assert_array_equal(colors[0], self.tile)

    def test_filtered_materials_are_not_averaged_together(self):
        atlas = PeriodicAtlas([[8, 0], [0, 8]], resolution=8)
        image = np.concatenate([self.tile, 255-self.tile, self.tile], axis=1)
        masks = np.zeros((3, 8, 24), bool)
        for i in range(3): masks[i, :, i*8:(i+1)*8] = True
        atlas.add(image, masks)
        colors, valid, _ = atlas.maps()
        self.assertTrue(valid.all())
        np.testing.assert_array_equal(colors[1], 255-self.tile)

    def test_shared_solution_and_short_period_equivalent(self):
        atlas = PeriodicAtlas([[8, 0], [0, 8]], resolution=8)
        atlas.add(self.tile, self.masks)
        markers = np.array([[1, 2], [4, 4], [6, 7]])
        for marker, rule in zip(markers, self.rules):
            x, y = (marker-[3, 2]) % 8
            rule['colors'] = ['#%02X%02X%02X' % tuple(self.tile[y, x])]
        row = translation_candidates(atlas, markers+.5, self.rules, (7, 0))[0]
        self.assertTrue(row['accepted']); self.assertEqual(row['maximum'], 0)
        np.testing.assert_allclose(row['phase'], [3/8, 2/8])
        self.assertEqual(abs(row['dx']), 4); self.assertEqual(row['dy'], 2)
        self.assertFalse(row['verified'])

    def test_unfolded_cycle_respects_execution_radius(self):
        atlas = PeriodicAtlas([[8, 0], [0, 8]], resolution=8)
        atlas.add(self.tile, self.masks)
        markers = np.array([[1, 2], [4, 4], [6, 7]])
        for marker, rule in zip(markers, self.rules):
            x, y = (marker-[3, 2]) % 8
            rule['colors'] = ['#%02X%02X%02X' % tuple(self.tile[y, x])]
        rows = translation_candidates(atlas, markers+.5, self.rules, (0, 0),
                                       limit=64, cycle_radius=2, max_move=9)
        self.assertTrue(rows)
        self.assertTrue(all(np.hypot(r['dx'], r['dy']) <= 9 for r in rows))
        self.assertTrue(all(np.isfinite(r['dx']) and np.isfinite(r['dy']) for r in rows))

    def test_missing_and_conflicting_pixels_do_not_become_candidates(self):
        atlas = PeriodicAtlas([[8, 0], [0, 8]], resolution=8)
        self.assertEqual(translation_candidates(atlas, [[0, 0]]*3, self.rules), [])
        atlas.add(np.zeros_like(self.tile), self.masks)
        atlas.add(np.full_like(self.tile, 255), self.masks)
        self.assertEqual(translation_candidates(atlas, [[0, 0]]*3, self.rules), [])

    def test_lower_center_color_error_precedes_landing_safety(self):
        atlas=PeriodicAtlas([[32,0],[0,32]],resolution=32)
        image=np.full((32,32,3),100,np.uint8)
        image[3:12,3:12]=34
        image[22,22]=32
        atlas.add(image,np.ones((3,32,32),bool))
        rules=[dict(enabled=i==0,colors=['#202020'],exact=False,tolerance=8) for i in range(3)]
        raw=translation_candidates(atlas,[[.5,.5]]*3,rules)[0]
        robust_rows=translation_candidates(atlas,[[.5,.5]]*3,rules,landing_radius=1.)
        self.assertEqual(raw['colors'][0],'#202020')
        self.assertEqual(robust_rows[0]['colors'][0],'#202020')
        self.assertFalse(robust_rows[0]['landing_safe'])
        self.assertTrue(any(row['colors'][0]=='#222222' and row['landing_safe']
                            for row in robust_rows))

    def test_stable_landing_mask_wraps_the_period_boundary(self):
        atlas=PeriodicAtlas([[32,0],[0,32]],resolution=32)
        image=np.full((32,32,3),100,np.uint8)
        image[:,:3]=32;image[:,-3:]=32
        atlas.add(image,np.ones((3,32,32),bool))
        rules=[dict(enabled=i==0,colors=['#202020'],exact=False,tolerance=8) for i in range(3)]
        row=translation_candidates(atlas,[[.5,.5]]*3,rules,landing_radius=1.)[0]
        self.assertTrue(row['landing_safe']);self.assertEqual(row['dx'],0)

    def test_cancel_and_invalid_geometry(self):
        with self.assertRaises(ValueError): PeriodicAtlas([[8, 0], [0, 0]])
        atlas = PeriodicAtlas([[8, 0], [0, 8]], resolution=8)
        with self.assertRaises(InterruptedError):
            translation_candidates(atlas, [[0, 0]]*3, self.rules, cancelled=lambda: True)

    def test_resampling_preserves_linear_ramp_at_fractional_positions(self):
        atlas=PeriodicAtlas([[16,0],[0,16]],resolution=16)
        y,x=np.mgrid[:20,:20]
        image=np.stack((x*5,y*5,(x+y)*3),axis=-1).astype(np.uint8)
        masks=np.zeros((3,20,20),bool);masks[:,:16,:16]=True
        atlas.add_resampled(image,masks)
        values,valid=atlas.sample(0,[[5.5,7.5],[0,0]])
        self.assertTrue(valid[0]);self.assertFalse(valid[1])
        np.testing.assert_allclose(values[0],[27.5,37.5,39],atol=.5)

    def test_resampling_excludes_ui_in_bilinear_stencil(self):
        atlas=PeriodicAtlas([[16,0],[0,16]],resolution=16)
        image=np.full((16,16,3),80,np.uint8);image[:,4]=255
        masks=np.ones((3,16,16),bool);masks[:,:,4]=False
        atlas.add_resampled(image,masks)
        colors,valid,_=atlas.maps()
        self.assertFalse(valid[:,:,3:5].any())
        self.assertTrue((colors[valid]==80).all())

    def test_native_frame_sample_list_exceeds_opencv_dimension_limit(self):
        atlas=PeriodicAtlas([[8,0],[0,8]],resolution=8)
        atlas.add(np.full_like(self.tile,80),self.masks)
        values,valid=atlas.sample(0,np.tile([3.5,3.5],(40000,1)))
        self.assertTrue(valid.all());self.assertTrue((values==80).all())

    def test_review_exports_valid_maps_and_serializable_predictions(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            Image.fromarray(self.tile).save(root/'frame.png')
            Image.fromarray(np.full((8, 8), 255, np.uint8)).save(root/'mask.png')
            data = dict(basis=[[8, 0], [0, 8]], origin=[0, 0], resolution=8,
                        frames=[dict(image='frame.png', masks=['mask.png']*3, measured_translation=[0, 0])],
                        markers=[[0, 0]]*3, current_translation=[0, 0], rules=self.rules)
            (root/'input.json').write_text(json.dumps(data), encoding='utf-8')
            result = review(root/'input.json', root/'output')
            self.assertGreater(result['coverage'][0]['coverage'], .5)
            self.assertTrue(result['candidates'])
            self.assertFalse(json.loads((root/'output/review.json').read_text())['verified'])
            with Image.open(root/'output/region-1.png') as im:
                self.assertEqual(im.mode, 'RGBA')


if __name__ == '__main__': unittest.main()
