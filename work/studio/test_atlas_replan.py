import unittest
import numpy as np
from atlas_replan import MeasuredAtlas,reachable_candidates
from atlas_pose import homogeneous,candidate_pose
from periodic_atlas import PeriodicAtlas
from vision import error


class ReplanTests(unittest.TestCase):
    def test_rotated_scaled_capture_and_rebased_choice_predictions(self):
        rng=np.random.default_rng(329)
        atlas=PeriodicAtlas([[36,0],[0,40]],resolution=40)
        image=rng.integers(0,256,(45,43,3),dtype=np.uint8)
        atlas.add_resampled(image,np.ones((3,45,43),bool))
        atlas=atlas.snapshot()
        angle=.35;scale=.99**35
        matrix=scale*np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
        actual=homogeneous(np.c_[matrix,[9.,-5.]])
        reference=homogeneous([[1,0,-7],[0,1,14]])
        offset=[5.,10.];markers=np.array([[20,25],[35,40],[48,32]])
        board=(10,15,70,75)
        rules=[dict(enabled=True,colors=['#808080'],exact=i==0,tolerance=8) for i in range(3)]
        rows=reachable_candidates(atlas,offset,actual,markers,board,rules,7,reference_pose=reference)
        self.assertTrue(rows)
        for row in rows:
            shift=np.asarray(row['remaining_translation'])
            np.testing.assert_array_equal(shift,np.rint(shift))
            target=candidate_pose(row,board)@reference
            inv=np.linalg.inv(target)
            source=(markers-board[:2]-target[:2,2])@inv[:2,:2].T
            for region in range(3):
                values,supported=atlas.sample(region,[source[region]],offset)
                self.assertTrue(supported[0])
                expected='#%02X%02X%02X'%tuple(np.rint(values[0]).clip(0,255).astype(int))
                self.assertEqual(row['colors'][region],expected)
                self.assertAlmostEqual(row['deltas'][region],error(expected,['#808080'],False),places=4)
            np.testing.assert_allclose(target[:2,:2],(actual@reference)[:2,:2])

    def test_cancellation_before_search_never_returns_a_candidate(self):
        atlas=PeriodicAtlas([[8,0],[0,8]],resolution=8).snapshot()
        def stop():raise InterruptedError('F9')
        with self.assertRaises(InterruptedError):
            reachable_candidates(atlas,[0,0],np.eye(3),[[1,2]]*3,(0,0,8,8),
                [dict(enabled=True,exact=False,colors=['#000000'],tolerance=8)]*3,0,check=stop)


if __name__=='__main__':unittest.main()
