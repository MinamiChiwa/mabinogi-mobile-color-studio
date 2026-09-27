import unittest
import numpy as np
from periodic_atlas import PeriodicAtlas,translation_candidates


class SnapshotTests(unittest.TestCase):
    def fixture(self):
        atlas=PeriodicAtlas([[17,1],[-2,19]],resolution=16)
        rng=np.random.default_rng(914)
        image=rng.integers(0,256,(31,37,3),dtype=np.uint8)
        masks=rng.random((3,31,37))>.05
        atlas.add_resampled(image,masks,(1.2,-2.3))
        atlas.add_resampled(image,masks,(1.25,-2.25))
        return atlas,image,masks

    def test_snapshot_preserves_maps_sampling_and_quality(self):
        atlas,_,_=self.fixture();snapshot=atlas.snapshot()
        for region in (None,0,1,2):
            for threshold in (8,0,100):
                for a,b in zip(atlas.maps(threshold,region),snapshot.maps(threshold,region)):
                    np.testing.assert_array_equal(a,b)
        points=np.random.default_rng(2).uniform(-30,40,(400,2))
        for region in range(3):
            for a,b in zip(atlas.sample(region,points,(2,3)),snapshot.sample(region,points,(2,3))):
                np.testing.assert_array_equal(a,b)
        self.assertEqual(atlas.report(),snapshot.report())

    def test_snapshot_is_immutable_and_not_stale_after_new_accumulation(self):
        atlas,image,masks=self.fixture();snapshot=atlas.snapshot()
        before=[a.copy() for a in snapshot.maps()];counts=snapshot.count.copy()
        atlas.add_resampled(255-image,masks,(1.2,-2.3))
        np.testing.assert_array_equal(snapshot.count,counts)
        self.assertFalse(np.array_equal(atlas.count,counts))
        for a,b in zip(before,snapshot.maps()):np.testing.assert_array_equal(a,b)
        for array in (*snapshot.maps(),snapshot.count,snapshot.basis):
            with self.assertRaises(ValueError):array.flat[0]=0

    def test_same_candidates_including_wrap_constraints(self):
        atlas=PeriodicAtlas([[8,0],[0,8]],resolution=8)
        image=np.random.default_rng(718).integers(0,256,(8,8,3),dtype=np.uint8)
        atlas.add(image,np.ones((3,8,8),bool));snapshot=atlas.snapshot()
        rules=[dict(enabled=True,colors=['#646464','#804020'],exact=False,tolerance=8)]*3
        args=([[3,4],[13,7],[25,20]],rules,(7,-12))
        expected=translation_candidates(atlas,*args,max_move=30)
        self.assertTrue(expected)
        self.assertEqual(expected,
                         translation_candidates(snapshot,*args,max_move=30))


if __name__=='__main__':unittest.main()
