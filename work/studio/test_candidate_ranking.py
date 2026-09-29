import unittest

import numpy as np

from candidate_ranking import candidate_order, candidate_rank,candidate_quality


class CandidateRankingTests(unittest.TestCase):
    def test_exact_priority_within_the_same_family_envelope(self):
        rows=[
            dict(id=2,exact_matches=2,exact_maximum=0,exact_average=0,maximum=98.58,average=33.89),
            dict(id=7,exact_matches=1,exact_maximum=2,exact_average=1,maximum=39.66,average=14.35),
        ]
        self.assertEqual(min(rows,key=candidate_rank)['id'],2)

    def test_balanced_exact_error_matches_vectorized_search_order(self):
        rows=[
            dict(id=2,exact_matches=1,exact_maximum=35,exact_average=17.5,
                 maximum=35,average=12,accepted=False,dx=0,dy=0),
            dict(id=7,exact_matches=0,exact_maximum=5,exact_average=4,
                 maximum=40,average=16,accepted=False,dx=1,dy=1),
        ]
        expected=[row['id'] for row in sorted(rows,key=candidate_rank)]
        order=candidate_order(
            [row['exact_matches'] for row in rows],
            [row['maximum'] for row in rows],
            [row['average'] for row in rows],
            [row['accepted'] for row in rows],
            [row.get('landing_safe',False) for row in rows],
            [row.get('landing_maximum',row['maximum']) for row in rows],
            [np.hypot(row['dx'],row['dy']) for row in rows],
            exact_maximum=[row['exact_maximum'] for row in rows],
            exact_average=[row['exact_average'] for row in rows],
        )
        self.assertEqual(expected,[7,2])
        self.assertEqual([rows[i]['id'] for i in order],expected)

    def test_worst_exact_region_precedes_mean_error(self):
        uneven=dict(id=0,exact_matches=1,exact_maximum=10,exact_average=5,maximum=10,average=5)
        balanced=dict(id=1,exact_matches=0,exact_maximum=8,exact_average=8,maximum=8,average=8)
        self.assertEqual(min([uneven,balanced],key=candidate_rank)['id'],1)

    def test_similar_only_candidates_keep_overall_error_order(self):
        rows=[dict(id=0,maximum=12,average=5),dict(id=1,maximum=8,average=7)]
        self.assertEqual(min(rows,key=candidate_rank)['id'],1)

    def test_verified_result_and_prediction_use_the_same_quality_metrics(self):
        from atlas_execution import verify_result
        rules=[dict(enabled=i<2,exact=True,colors=['#FFFFFF'],tolerance=0) for i in range(3)]
        candidate=dict(id=0,colors=['#FFFFFF','#008000',None],deltas=[0,80,None])
        uneven=verify_result(candidate,['#FFFFFF','#008000',None],rules)
        balanced=verify_result(candidate,['#EEEEEE','#EEEEEE',None],rules)
        self.assertEqual(uneven['exact_matches'],1)
        self.assertEqual(balanced['exact_matches'],0)
        self.assertLess(candidate_quality(balanced),candidate_quality(uneven))

    def test_color_error_precedes_landing_safety(self):
        unsafe=dict(id=0,exact_matches=1,maximum=0,average=0,
                    accepted=True,landing_safe=False,landing_maximum=20)
        safe=dict(id=1,exact_matches=1,maximum=2,average=2,
                  accepted=True,landing_safe=True,landing_maximum=3)
        self.assertEqual(min([unsafe,safe],key=candidate_rank)['id'],0)

    def test_cross_family_fallback_orders_by_actual_error(self):
        rows=[
            dict(id=0,cross_family_fallback=True,maximum=42,average=20,
                 family_maximum=.2,landing_maximum=1,dx=0,dy=0),
            dict(id=1,cross_family_fallback=True,maximum=35,average=30,
                 family_maximum=.3,landing_maximum=1,dx=1,dy=1),
        ]
        self.assertEqual(min(rows,key=candidate_rank)['id'],1)


if __name__=='__main__':
    unittest.main()
