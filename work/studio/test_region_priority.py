import unittest
import numpy as np
from region_priority import priority_components, vector_priority_components, priority_indices
from hex_refinement import score_codes
from native_live.compromise import observed_quality, predicted_quality
from candidate_ranking import candidate_rank, candidate_order


def rules(order=(1, 2, 3), exact=True):
    return [dict(enabled=True, colors=['#000000'], exact=exact, tolerance=8., priority=p) for p in order]


class RegionPriorityTests(unittest.TestCase):
    def test_priority_swap_changes_compromise_but_never_full_acceptance(self):
        a = ['#000000', '#FFFFFF', '#FFFFFF']
        b = ['#FFFFFF', '#000000', '#000000']
        self.assertLess(score_codes(a, rules())['rank'], score_codes(b, rules())['rank'])
        self.assertGreater(score_codes(a, rules((3, 1, 2)))['rank'], score_codes(b, rules((3, 1, 2)))['rank'])
        self.assertLess(score_codes(['#000000'] * 3, rules())['rank'], score_codes(a, rules())['rank'])

    def test_native_predicted_measured_and_scalar_visual_share_order(self):
        r = rules()
        a = ['#000000', '#FFFFFF', '#FFFFFF']; b = ['#FFFFFF', '#000000', '#000000']
        self.assertLess(observed_quality(a, r), observed_quality(b, r))
        pa, pb = score_codes(a, r), score_codes(b, r)
        self.assertLess(predicted_quality(pa, r), predicted_quality(pb, r))
        rows = [dict(id=i, maximum=max(p['deltas']), average=np.mean(p['deltas']), accepted=p['accepted'],
                     region_priority=priority_components(p['colors'], r, p['deltas'])) for i, p in enumerate((pa, pb))]
        self.assertEqual(min(rows, key=candidate_rank)['id'], 0)
        order = candidate_order([0, 0], [row['maximum'] for row in rows], [row['average'] for row in rows],
                                [False, False], [False, False], [100., 100.], [0., 0.],
                                region_priority=np.asarray([row['region_priority'] for row in rows]))
        self.assertEqual(list(order), [0, 1])

    def test_similar_uses_tolerance_before_color_polishing(self):
        r = rules(exact=False)
        a, b = ['#101010', '#000000', '#FFFFFF'], ['#000000', '#FFFFFF', '#000000']
        self.assertLess(score_codes(a, r)['rank'], score_codes(b, r)['rank'])

    def test_disabled_regions_and_alternatives_do_not_distort_order(self):
        r = rules(); r[0]['enabled'] = False; r[1]['colors'].append('#FFFFFF')
        a = [None, '#FFFFFF', '#000000']
        self.assertEqual(priority_components(a, r), (0, 0, 0., 0.))
        self.assertTrue(score_codes(a, r)['accepted'])

    def test_invalid_priorities_rejected_and_legacy_rules_unchanged(self):
        r = rules(); r[1]['priority'] = 1
        with self.assertRaises(ValueError): priority_indices(r)
        r = rules()
        for rule in r: rule.pop('priority')
        self.assertIsNone(priority_components(['#000000'] * 3, r))
        self.assertEqual(score_codes(['#000000'] * 3, r)['rank'], (False, 0., 0, 0.))

    def test_invalid_rules_and_distances_do_not_create_spurious_similar_hits(self):
        with self.assertRaises(ValueError):priority_indices([None,{},{}])
        r=rules(exact=False)
        colors=[np.zeros((1,3),dtype=np.uint8)]*3
        vector=vector_priority_components(colors,[[-1.],[np.nan],[np.inf]],r)
        scalar=priority_components(['#000000']*3,r,[-1.,np.nan,np.inf])
        np.testing.assert_equal(vector[0],scalar)

    def test_vector_matches_scalar_on_mixed_targets(self):
        from vision import lab, rgb
        r = rules((3, 1, 2), False); r[0]['exact'] = True
        codes = [['#000000', '#030303', '#AAAAAA'], ['#101010', '#FFFFFF', '#000000'], ['#000000'] * 3]
        colors = [np.asarray([rgb(codes[n][i]) for n in range(3)]) for i in range(3)]
        distances = [np.linalg.norm(lab(c) - lab([rgb('#000000')])[0], axis=1) for c in colors]
        vector = vector_priority_components(colors, distances, r)
        for i in range(3): np.testing.assert_allclose(vector[i], priority_components(codes[i], r))


if __name__ == '__main__': unittest.main()
