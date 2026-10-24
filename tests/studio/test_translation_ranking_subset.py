import unittest
from unittest.mock import patch
import numpy as np
from periodic_atlas import PeriodicAtlas, translation_candidates, _ranking_subset


class TranslationSubsetTests(unittest.TestCase):
    def test_lower_tier_is_removed_only_with_enough_distinct_colors(self):
        values=np.array([[10,0,0],[20,0,0],[30,0,0],[40,0,0]],np.uint8)
        self.assertEqual(_ranking_subset([values],[0],np.arange(4),
            [np.array([0,0,1,1])],2).tolist(),[0,1])
        values[1]=values[0]
        self.assertEqual(_ranking_subset([values],[0],np.arange(4),
            [np.array([0,0,1,1])],2).tolist(),[0,1,2,3])

    def test_bounded_probe_falls_back_without_losing_later_unique_colors(self):
        values=np.zeros((2048,3),np.uint8);values[1900]=[1,2,3]
        ids=np.arange(len(values));metric=np.r_[np.zeros(2000),np.ones(48)]
        np.testing.assert_array_equal(_ranking_subset([values],[0],ids,[metric],2),ids)

    def test_disabled_colors_cannot_supply_false_diversity(self):
        values=np.array([[1,0,0],[2,0,0],[3,0,0]],np.uint8)
        same=np.zeros_like(values)
        np.testing.assert_array_equal(_ranking_subset([same,values],[0],np.arange(3),
            [np.array([0,0,1])],2),np.arange(3))

    def test_full_candidate_outputs_equal_exhaustive_sort_across_rules_and_masks(self):
        rng=np.random.default_rng(929)
        for enabled_count in (1,2,3):
            for exact in (False,True):
                atlas=PeriodicAtlas([[31,2],[-1,29]],resolution=32)
                image=rng.integers(0,256,(44,42,3),dtype=np.uint8)
                atlas.add_resampled(image,rng.random((3,44,42))>.02)
                atlas=atlas.snapshot()
                rules=[dict(enabled=i<enabled_count,exact=exact and i<2,
                            colors=['#888888','#0080FF'],tolerance=8) for i in range(3)]
                kwargs=dict(integer_moves=True,landing_radius=1.,max_move=25,limit=8)
                args=(atlas,[[8,9],[19,24],[27,13]],rules,[4.7,-2.3])
                actual=translation_candidates(*args,**kwargs)
                with patch('periodic_atlas._ranking_subset',side_effect=lambda p,e,ids,k,l:ids):
                    expected=translation_candidates(*args,**kwargs)
                self.assertEqual(actual,expected,(enabled_count,exact))


if __name__=='__main__':unittest.main()
