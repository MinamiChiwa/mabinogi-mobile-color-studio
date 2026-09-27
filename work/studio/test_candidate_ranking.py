import unittest

import numpy as np

from candidate_ranking import candidate_order, candidate_rank


class CandidateRankingTests(unittest.TestCase):
    def test_exact_match_count_still_precedes_overall_color_error(self):
        rows=[
            dict(id=2,exact_matches=2,maximum=98.58,average=33.89),
            dict(id=7,exact_matches=1,maximum=39.66,average=14.35),
        ]
        self.assertEqual(min(rows,key=candidate_rank)['id'],2)

    def test_overall_error_tie_break_matches_vectorized_search_order(self):
        # Reproduces the user's run: id 2 had a slightly better Exact-zone
        # score, while id 7 had much lower color error across all enabled zones.
        rows=[
            dict(id=2,exact_matches=1,exact_maximum=3.0948,exact_average=1.5474,
                 maximum=98.5834,average=33.8927,accepted=False,dx=0,dy=0),
            dict(id=7,exact_matches=1,exact_maximum=3.3818,exact_average=1.6909,
                 maximum=39.6576,average=14.3465,accepted=False,dx=1,dy=1),
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
        )
        self.assertEqual(expected,[7,2])
        self.assertEqual([rows[i]['id'] for i in order],expected)

    def test_color_error_precedes_landing_safety(self):
        unsafe=dict(id=0,exact_matches=1,maximum=0,average=0,
                    accepted=True,landing_safe=False,landing_maximum=20)
        safe=dict(id=1,exact_matches=1,maximum=2,average=2,
                  accepted=True,landing_safe=True,landing_maximum=3)
        self.assertEqual(min([unsafe,safe],key=candidate_rank)['id'],0)


if __name__=='__main__':
    unittest.main()
