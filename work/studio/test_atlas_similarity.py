import unittest
import numpy as np
from periodic_atlas import PeriodicAtlas, translation_candidates
from atlas_similarity import similarity_candidates, captured_scale_levels
from vision import rgb


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
        self.assertTrue(all(r['deltas'][2]>8 for r in rows))
        self.assertEqual([r['maximum'] for r in rows],sorted(r['maximum'] for r in rows))

    def test_compromise_never_uses_an_unobserved_region(self):
        self.atlas.count[2]=0
        self.assertEqual(self.solve(include_compromises=True),[])

    def test_no_exact_target_uses_nearby_colors_without_changing_acceptance(self):
        self.rules[2]['colors']=['#0000FE']
        self.assertEqual(self.solve(),[])
        rows=self.solve(include_compromises=True)
        self.assertTrue(rows)
        self.assertFalse(any(r['accepted'] for r in rows))

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

    def test_zoom_levels_require_this_sessions_measured_capture_range(self):
        levels,tick=captured_scale_levels([dict(kind='sampling_zoom',steps=4,scale=1.01**4)])
        np.testing.assert_allclose(levels,1.01**-np.arange(5,dtype=float))
        self.assertAlmostEqual(tick,np.log(1.01))
        self.assertEqual(captured_scale_levels([]),([1.],None))


if __name__=='__main__':unittest.main()
