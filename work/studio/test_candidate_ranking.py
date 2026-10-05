import unittest

import numpy as np

from candidate_ranking import (candidate_order, candidate_rank, progressive_candidate_rank,
                               candidate_quality)


class CandidateRankingTests(unittest.TestCase):
    def test_progressive_rank_prioritizes_worst_error_then_hits_then_cost(self):
        rows=[
            dict(id=1,maximum=4,average=2,total=6,exact_matches=0,dx=0,dy=0,
                 action_cost=1,action_risk=1),
            dict(id=2,maximum=4,average=2,total=6,exact_matches=1,dx=20,dy=0,
                 action_cost=20,action_risk=1),
            dict(id=3,maximum=5,average=1,total=3,exact_matches=3,dx=0,dy=0,
                 action_cost=0,action_risk=0),
        ]
        self.assertEqual(min(rows,key=progressive_candidate_rank)['id'],2)

    def test_progressive_rank_unknown_action_risk_is_last_tie_break(self):
        known=dict(id=1,maximum=2,average=1,total=3,exact_matches=1,action_cost=1,action_risk=2)
        unknown=dict(id=2,maximum=2,average=1,total=3,exact_matches=1,action_cost=1,action_risk=None)
        self.assertEqual(min([known,unknown],key=progressive_candidate_rank)['id'],known['id'])
    def test_verified_recovery_uses_observed_acceptance_not_incomplete_route(self):
        recovered=dict(verified=True,accepted=False,observed_accepted=True,
                       maximum=5.,average=4.,landing_safe=False,landing_maximum=80.)
        observation=dict(verified=True,accepted=True,maximum=5.,average=4.)
        self.assertEqual(candidate_quality(recovered),candidate_quality(observation))

    def test_actual_result_does_not_reuse_the_forecast_neighborhood(self):
        actual=dict(id=0,verified=True,accepted=False,maximum=5.,average=4.)
        self.assertEqual(candidate_quality(actual),candidate_quality(
            dict(actual,landing_safe=False,landing_radius=1.,landing_maximum=None)))

    def test_overall_quality_precedes_exact_hits(self):
        rows=[
            dict(id=2,exact_matches=2,exact_maximum=0,exact_average=0,maximum=98.58,average=33.89),
            dict(id=7,exact_matches=1,exact_maximum=2,exact_average=1,maximum=39.66,average=14.35),
        ]
        self.assertEqual(min(rows,key=candidate_rank)['id'],7)

    def test_exact_hits_match_vectorized_search_order_within_family(self):
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
        self.assertEqual(expected,[2,7])
        self.assertEqual([rows[i]['id'] for i in order],expected)

    def test_equal_exact_hits_balance_the_worst_enabled_region(self):
        uneven=dict(id=0,exact_matches=0,exact_maximum=3,exact_average=3,maximum=35,average=12)
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

    def test_complete_accepted_neighborhood_precedes_brittle_center_hit(self):
        unsafe=dict(id=0,exact_matches=1,maximum=0,average=0,
                    accepted=True,landing_safe=False,landing_maximum=20)
        safe=dict(id=1,exact_matches=1,maximum=2,average=2,
                  accepted=True,landing_safe=True,landing_maximum=3)
        self.assertEqual(min([unsafe,safe],key=candidate_rank)['id'],1)

    def test_actual_white_tolerances_prioritize_fully_accepted_result(self):
        from atlas_execution import verify_result
        rules=[dict(enabled=i<2,exact=False,colors=['#FFFFFF'],tolerance=t)
               for i,t in enumerate((6,20,8))]
        candidate=dict(id=0,colors=['#FFFFFF']*3,deltas=[0]*3)
        missed=verify_result(candidate,['#ECECEC','#ECECEC',None],rules)
        passed=verify_result(candidate,['#F1F1F1','#E6E6E6',None],rules)
        self.assertFalse(missed['accepted']);self.assertTrue(passed['accepted'])
        self.assertLess(missed['maximum'],passed['maximum'])
        self.assertLess(candidate_quality(passed),candidate_quality(missed))

    def test_two_near_whites_beat_one_exact_and_one_darker_same_family(self):
        from atlas_execution import verify_result
        rules=[dict(enabled=i<2,exact=True,colors=['#FFFFFF'],tolerance=0) for i in range(3)]
        candidate=dict(id=0,colors=['#FFFFFF']*3,deltas=[0]*3)
        uneven=verify_result(candidate,['#FFFFFF','#C7C7C7',None],rules)
        balanced=verify_result(candidate,['#FAFAFA','#FAFAFA',None],rules)
        self.assertTrue(uneven['family_consistent'] and balanced['family_consistent'])
        self.assertEqual(uneven['exact_matches'],1)
        self.assertEqual(balanced['exact_matches'],0)
        self.assertLess(candidate_quality(balanced),candidate_quality(uneven))

    def test_compromise_neighborhood_risk_is_not_replaced_by_center_error(self):
        fragile=dict(id=0,maximum=5,average=4,accepted=False,landing_safe=False,landing_maximum=50)
        robust=dict(id=1,maximum=6,average=5,accepted=False,landing_safe=False,landing_maximum=7)
        self.assertEqual(min([fragile,robust],key=candidate_rank)['id'],1)
        # The pair-seed screening call has no all-regions safety assertion.
        order=candidate_order([0,0],[5,6],[4,5],[False,False],False,[50,7],[0,0])
        self.assertEqual(order.tolist(),[1,0])

    def test_exact_is_a_tie_break_only_after_overall_error(self):
        near=dict(id=0,maximum=6,average=3,exact_matches=0)
        exact=dict(id=1,maximum=6,average=3,exact_matches=1)
        self.assertLess(candidate_quality(exact),candidate_quality(near))
        self.assertLess(candidate_quality(dict(near,maximum=5.999999)),candidate_quality(exact))

    def test_family_boundary_does_not_override_better_overall_result(self):
        inside=dict(id=0,maximum=20,average=10,family_maximum=0)
        outside=dict(id=1,maximum=5,average=3,family_maximum=.00001)
        self.assertLess(candidate_quality(outside),candidate_quality(inside))
        self.assertLess(candidate_quality(inside),candidate_quality(dict(inside,family_maximum=.1)))

    def test_missing_or_nonfinite_neighborhood_is_unknown_not_zero_risk(self):
        known=dict(id=0,maximum=8,average=5,landing_maximum=9,landing_safe=False)
        for value in (None,np.nan,np.inf):
            unknown=dict(id=1,maximum=1,average=1,accepted=True,
                         landing_maximum=value,landing_safe=True)
            self.assertLess(candidate_quality(known),candidate_quality(unknown))
        malformed=dict(id=2,maximum=np.nan,average=1,accepted=True,exact_matches=np.nan)
        self.assertLess(candidate_quality(known),candidate_quality(malformed))

    def test_random_scalar_vector_order_with_uncertainty_and_duplicate_scores(self):
        rng=np.random.default_rng(20260929)
        rows=[]
        for i in range(180):
            maximum=float(rng.integers(15));risk=rng.choice([None,np.nan,maximum,maximum+5])
            row=dict(id=i,maximum=maximum,average=float(rng.integers(8)),
                     exact_matches=int(rng.integers(4)),accepted=bool(rng.integers(2)),
                     exact_maximum=float(rng.integers(15)),exact_average=float(rng.integers(8)),
                     family_maximum=float(rng.choice([0,.01,1.])),family_average=0.,dx=i%3,dy=0)
            if i%3:row.update(landing_maximum=risk,landing_safe=bool(rng.integers(2)))
            rows.append(row)
        rng.shuffle(rows)
        values=lambda key,default=None:[r.get(key,default) for r in rows]
        order=candidate_order(values('exact_matches'),values('maximum'),values('average'),
            values('accepted'),values('landing_safe',False),
            [r.get('landing_maximum',r['maximum']) for r in rows],values('dx'),
            exact_maximum=values('exact_maximum'),exact_average=values('exact_average'),
            family_maximum=values('family_maximum'),family_average=values('family_average'),
            neighborhood_present=['landing_safe' in r for r in rows],candidate_ids=values('id'))
        self.assertEqual([rows[i]['id'] for i in order],
                         [r['id'] for r in sorted(rows,key=candidate_rank)])

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
