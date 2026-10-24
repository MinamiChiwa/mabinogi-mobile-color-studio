import unittest
import numpy as np
from periodic_atlas import PeriodicAtlas, translation_candidates
from atlas_similarity import similarity_candidates, captured_scale_levels
from vision import rgb
from candidate_ranking import candidate_rank


class SimilarityTests(unittest.TestCase):
    def setUp(self):
        self.atlas=PeriodicAtlas([[32,0],[0,32]],resolution=32)
        self.points=np.array([[29.5,6.5],[33.5,6.5],[31.5,14.5]])
        self.targets=['#FF0000','#00FF00','#0000FF']
        for i,p in enumerate(self.points):
            image=np.full((32,32,3),100,np.uint8)
            x,y=np.floor(p).astype(int)%32; image[y,x]=rgb(self.targets[i])
            masks=np.zeros((3,32,32),bool); masks[i]=True
            self.atlas.add(image,masks)
        self.rules=[dict(enabled=True,colors=[c],exact=True,tolerance=0) for c in self.targets]
        self.markers=np.array([[15.,15.],[15.,18.],[9.,16.5]])
        self.current=np.array([57.,40.])

    def solve(self,**kwargs):
        return similarity_candidates(self.atlas,self.markers,self.rules,self.current,(64,64),
                                     scale_bounds=(.7,.8),**kwargs)

    def test_color_first_solver_finds_three_point_rotation_scale_across_seam(self):
        translations=translation_candidates(self.atlas,self.markers,self.rules,self.current)
        self.assertFalse(any(row['accepted'] for row in translations))
        rows=self.solve(); self.assertTrue(rows)
        row=rows[0]
        self.assertFalse(row['verified']); self.assertFalse(row['execution_verified'])
        self.assertAlmostEqual(row['scale'],.75)
        self.assertAlmostEqual(row['angle'],90.)
        matrix=np.array(row['matrix'])
        reference_sources=(self.markers-matrix[:,2])@np.linalg.inv(matrix[:,:2]).T
        for i,point in enumerate(reference_sources-self.current):
            values,valid=self.atlas.sample(i,[point])
            self.assertTrue(valid[0]); np.testing.assert_allclose(values[0],rgb(self.targets[i]))

    def test_third_region_must_share_the_transform(self):
        self.markers[2]+=[0,2]
        self.assertEqual(self.solve(),[])

    def test_compromise_keeps_supported_third_region_miss_with_original_error(self):
        self.markers[2]+=[0,2]
        rows=self.solve(include_compromises=True)
        self.assertTrue(rows)
        self.assertFalse(any(r['accepted'] or r['verified'] for r in rows))
        self.assertTrue(all(max(r['deltas'])>8 for r in rows))
        self.assertEqual(rows,sorted(rows,key=candidate_rank))
        # Any pair may anchor a compromise; the third region is no longer
        # unconditionally sacrificed to the first two regions.
        self.assertTrue(any(r['deltas'][2]==0 for r in rows))

    def test_compromise_never_uses_an_unobserved_region(self):
        self.atlas.count[2]=0
        self.assertEqual(self.solve(include_compromises=True),[])

    def test_no_exact_target_uses_nearby_colors_without_changing_acceptance(self):
        self.rules[2]['colors']=['#0000FE']
        self.assertEqual(self.solve(),[])
        diagnostics={}
        rows=similarity_candidates(self.atlas,self.markers,self.rules,self.current,(64,64),
                                   scale_bounds=(.7,.8),include_compromises=True,
                                   diagnostics=diagnostics)
        self.assertTrue(rows)
        self.assertFalse(any(r['accepted'] for r in rows))
        self.assertGreater(diagnostics['exact_fallback_pool'],0)
        self.assertAlmostEqual(rows[0]['exact_maximum'],
                               min(row['exact_maximum'] for row in rows))

    def test_disabled_region_does_not_constrain_geometry_or_colors(self):
        self.rules[2]=dict(enabled=False,colors=[],exact=False,tolerance=8)
        self.markers[2]+=[0,2]
        self.assertTrue(self.solve())

    def test_angle_bound_and_cancellation_are_enforced(self):
        self.assertEqual(self.solve(max_angle=0),[])
        with self.assertRaises(InterruptedError):self.solve(cancelled=lambda:True)

    def test_narrow_color_hits_are_not_claimed_to_be_stable_landings(self):
        rows=self.solve()
        self.assertFalse(any(v['landing_safe'] for v in rows))

    def test_discrete_scale_is_resampled_instead_of_reusing_continuous_scores(self):
        self.assertTrue(self.solve(scale_levels=[.75]))
        self.assertEqual(self.solve(scale_levels=[.7,.8]),[])

    def test_unreachable_exact_pair_does_not_hide_other_region_pairs(self):
        self.points=np.array([[5.5,5.5],[5.5,5.5],[15.5,5.5]])
        atlas=PeriodicAtlas([[32,0],[0,32]],resolution=32)
        for i,p in enumerate(self.points):
            image=np.full((32,32,3),100,np.uint8)
            x,y=np.floor(p).astype(int);image[y,x]=rgb(self.targets[i])
            masks=np.zeros((3,32,32),bool);masks[i]=True;atlas.add(image,masks)
        markers=np.array([[12.,12.],[12.,15.],[12.,19.5]])
        diag={}
        rows=similarity_candidates(atlas,markers,self.rules,(0,0),(32,32),
            scale_bounds=(.7,.8),scale_levels=[.75],include_compromises=True,
            diagnostics=diag)
        self.assertTrue(rows)
        self.assertGreaterEqual(rows[0]['exact_matches'],2)
        self.assertEqual(rows[0]['deltas'][0],0)
        self.assertEqual(rows[0]['deltas'][2],0)
        self.assertEqual(set(diag['pair_evaluated_transforms']),{'1-2','1-3','2-3'})

    def test_two_unreachable_exact_islands_keep_one_exact_compromise(self):
        atlas=PeriodicAtlas([[32,0],[0,32]],resolution=32)
        for i in range(2):
            image=np.full((32,32,3),100,np.uint8)
            image[5,5]=rgb(self.targets[i])
            masks=np.zeros((3,32,32),bool);masks[i]=True;atlas.add(image,masks)
        rules=[dict(r,enabled=i<2) for i,r in enumerate(self.rules)]
        rows=similarity_candidates(atlas,self.markers,rules,(0,0),(32,32),
            scale_bounds=(.7,.8),scale_levels=[.75],include_compromises=True)
        self.assertTrue(rows)
        self.assertEqual(rows[0]['exact_matches'],1)
        self.assertFalse(rows[0]['accepted'])
        self.assertTrue(all(abs(row['scale']-.75)<1e-12 for row in rows))

    def test_zoom_levels_require_this_sessions_measured_capture_range(self):
        log=[dict(kind='sampling_zoom',steps=48,scale=1.01**48)]
        # UP-only observations cannot establish a reachable DOWN route.
        self.assertEqual(captured_scale_levels(log),([1.],None))
        log.append(dict(kind='zoom_calibration',passed=True,
                        down_log_step=-np.log(.99),up_log_step=np.log(1.01)))
        levels,tick=captured_scale_levels(log)
        np.testing.assert_allclose(levels,.99**np.arange(48,dtype=float))
        self.assertAlmostEqual(tick,-np.log(.99))
        self.assertGreaterEqual(levels[-1],1/1.01**48)
        self.assertGreater(abs(levels[35]-1.01**-35),.002)
        log[-1]['passed']=False
        self.assertEqual(captured_scale_levels(log),([1.],None))
        self.assertEqual(captured_scale_levels([]),([1.],None))


if __name__=='__main__':unittest.main()
