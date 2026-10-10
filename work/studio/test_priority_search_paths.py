"""Region priority must survive candidate pruning and measured recovery."""
import unittest
import numpy as np

from region_priority import priority_components


def rules(priorities=(1, 2, 3), enabled=(True, True, False)):
    return [dict(enabled=enabled[i], exact=True, colors=['#000000'],
                 tolerance=0., priority=priorities[i]) for i in range(3)]


class TradeoffAtlas:
    basis = np.diag([4., 4.])
    resolution = 4
    def sample(self, region, points, translation=(0, 0)):
        phase = np.mod(np.asarray(points)[:, 0], 4.)
        high_hit = np.isclose(phase, 1.)
        levels = np.where(high_hit, 0 if region == 0 else 255, 20)
        return np.repeat(levels[:, None], 3, axis=1), np.ones(len(points), bool)


class PrioritySearchPathTests(unittest.TestCase):
    @staticmethod
    def shortlist_rows(active):
        from vision import error, accepted
        from region_priority import priority_fields
        samples = [['#000000', '#202020', None],
                   ['#000000', '#303030', None],
                   ['#FFFFFF', '#000000', None]]
        rows = []
        for index, colors in enumerate(samples):
            deltas = [error(colors[i], rule['colors'], False) if rule['enabled'] else None
                      for i, rule in enumerate(active)]
            values = [value for value in deltas if value is not None]
            rows.append(dict(id=index, colors=colors, deltas=deltas,
                             maximum=max(values), average=sum(values)/len(values),
                             accepted=accepted(colors, active),
                             **priority_fields(colors, deltas, active)))
        return rows

    def test_priority_shortlist_tail_never_sacrifices_the_highest_material_hit(self):
        from atlas_similarity import select_color_candidates
        active = rules()
        rows = self.shortlist_rows(active)
        selected = select_color_candidates(rows, active, 2)
        self.assertEqual([row['id'] for row in selected], [0, 1])
        self.assertTrue(all(row['colors'][0] == '#000000' for row in selected))

    def test_legacy_shortlist_still_reserves_independent_exact_alternatives(self):
        from atlas_similarity import select_color_candidates
        active = [{key: value for key, value in row.items() if key != 'priority'} for row in rules()]
        selected = select_color_candidates(self.shortlist_rows(active), active, 2)
        self.assertEqual([row['id'] for row in selected], [0, 2])

    def test_translation_shortlist_preserves_high_priority_hit_before_balanced_error(self):
        from periodic_atlas import translation_candidates
        chosen = translation_candidates(TradeoffAtlas(), [[0., 0.]]*3,
                                        rules(), limit=1)[0]
        self.assertEqual(chosen['colors'][:2], ['#000000', '#FFFFFF'])
        self.assertEqual(chosen['region_priority'][:2], [0, 1])
        self.assertFalse(chosen['accepted'])

    def test_translation_without_priority_keeps_balanced_legacy_selection(self):
        from periodic_atlas import translation_candidates
        legacy = [{k: v for k, v in rule.items() if k != 'priority'} for rule in rules()]
        chosen = translation_candidates(TradeoffAtlas(), [[0., 0.]]*3,
                                        legacy, limit=1)[0]
        self.assertEqual(chosen['colors'][:2], ['#141414', '#141414'])
        self.assertNotIn('region_priority', chosen)

    def test_similarity_limit_keeps_high_priority_exact_material(self):
        from test_atlas_similarity import SimilarityTests
        fixture = SimilarityTests(); fixture.setUp()
        fixture.markers[2] += [0, 2]
        for rule, priority in zip(fixture.rules, (2, 3, 1)):
            rule['priority'] = priority
        chosen = fixture.solve(limit=1, include_compromises=True)[0]
        self.assertEqual(chosen['colors'][2], fixture.targets[2])
        self.assertEqual(chosen['region_priority'][0], 0)
        self.assertFalse(chosen['accepted'])

    def test_pose_rescore_replaces_obsolete_priority_with_new_colors(self):
        from atlas_pose_scoring import rescore_candidate
        old = dict(id=1, dx=0., dy=0., region_priority=[0, 0, 0, 0],
                   colors=['#000000']*3, deltas=[0.]*3)
        row = rescore_candidate(TradeoffAtlas(), [0., 0.], old, np.eye(3),
                                [[0., 0.]]*3, (0, 0, 4, 4), rules(),
                                pose_source='independent_test_pose')
        self.assertEqual(row['region_priority'],
                         list(priority_components(row['colors'], rules(), row['deltas'])))
        self.assertNotEqual(row['region_priority'], old['region_priority'])

    def test_verified_atlas_result_uses_actual_colors_for_priority(self):
        from atlas_execution import verify_result
        rule = rules()
        proposal = dict(id=1, colors=['#141414']*3, deltas=[1.]*3,
                        region_priority=[1, 1, 1., 1.])
        actual = ['#000000', '#FFFFFF', None]
        result = verify_result(proposal, actual, rule)
        self.assertEqual(result['region_priority'],
                         list(priority_components(actual, rule, result['actual_deltas'])))
        self.assertFalse(result['accepted'])

    def test_measured_legacy_best_protects_high_priority_hit(self):
        from best_result import ranking
        self.assertLess(ranking(['#000000', '#FFFFFF', None], rules()),
                        ranking(['#141414', '#141414', None], rules()))
        self.assertLess(ranking(['#000000', '#000000', None], rules()),
                        ranking(['#000000', '#FFFFFF', None], rules()))

    def test_native_periodic_nearest_retention_uses_same_priority_as_execution(self):
        from native_periodic_search import search_periodic_targets
        from test_native_periodic_search import PeriodicSearchTests
        from native_live.compromise import predicted_quality
        fixture = PeriodicSearchTests()
        session = fixture.session()
        active = rules(priorities=(3, 2, 1), enabled=(True, True, True))
        result = search_periodic_targets(session, active, minimum_scale=.5,
                                         maximum_scale=3., top_k=16,
                                         time_budget_seconds=3.)
        rows = result['nearest_candidates']
        self.assertTrue(rows)
        quality = [predicted_quality(row['prediction'], active) for row in rows]
        self.assertEqual(quality, sorted(quality))

    def test_seed_candidate_cap_starts_with_high_priority_region(self):
        from native_target_seeds import target_seed_poses
        from test_native_periodic_search import PeriodicSearchTests
        session = PeriodicSearchTests().session()
        active = rules(priorities=(3, 1, 2), enabled=(True, True, True))
        row = target_seed_poses(session, active, max_candidates=1,
                                pixels_per_region=1)['seeds'][0]
        self.assertEqual(row['anchor_region'], 1)

    def test_prioritized_restoration_never_selects_an_incomplete_observation(self):
        from best_result import BestResult, ranking
        best = BestResult(rules())
        best.frames = {0: np.zeros((1, 1, 3), np.uint8), 1: np.ones((1, 1, 3), np.uint8)}
        best.records = [dict(rank=ranking(['#000000', '#FFFFFF', None], rules())),
                        dict(rank=ranking(['#000000', None, None], rules()))]
        best.target_index = 0
        self.assertFalse(best.next_target())


if __name__ == '__main__':
    unittest.main()
