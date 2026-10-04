import unittest

import numpy as np

from hex_feedback_search import (
    HexFeedbackError,
    NeighborhoodLimits,
    SearchDeadlineExceeded,
    UnstableHexRead,
    candidate_poses,
    neighborhood_offsets,
    rank_observations,
    retain_best,
    score_observation,
    stable_hex_read,
)


def _rules(enabled=True, tolerance=2):
    return [dict(enabled=enabled, colors=["#646464"], exact=False,
                 tolerance=tolerance) for _ in range(3)]


class Adapter:
    def __init__(self, values):
        self.values = list(values)
        self.index = 0
        self.now = 0.0
        self.frames = 0
        self.pauses = []

    def check(self):
        return None

    def capture(self):
        frame = self.frames
        self.frames += 1
        return frame

    def read_codes(self, _frame):
        value = self.values[min(self.index, len(self.values) - 1)]
        self.index += 1
        return value

    def pause(self, seconds):
        self.pauses.append(seconds)
        self.now += seconds


class HexFeedbackSearchTests(unittest.TestCase):
    def test_stable_read_normalizes_and_keeps_disabled_card(self):
        rules = _rules()
        rules[1]["enabled"] = False
        adapter = Adapter([
            ["646464", None, "#646464"],
            ["#646464", "not-used", "646464"],
        ])
        result = stable_hex_read(adapter, rules, pause=.15)
        self.assertEqual(result["codes"], ["#646464", None, "#646464"])
        self.assertTrue(result["stable"])
        self.assertEqual(adapter.pauses, [.15])

    def test_unstable_enabled_read_is_rejected(self):
        adapter = Adapter([["#646464"] * 3, ["#656464"] * 3])
        with self.assertRaises(UnstableHexRead):
            stable_hex_read(adapter, _rules())

    def test_missing_enabled_read_is_rejected(self):
        adapter = Adapter([[None, "#646464", "#646464"]] * 2)
        with self.assertRaisesRegex(HexFeedbackError, "could not be read"):
            stable_hex_read(adapter, _rules())

    def test_deadline_is_checked_before_capture(self):
        adapter = Adapter([["#646464"] * 3] * 2)
        with self.assertRaises(SearchDeadlineExceeded):
            stable_hex_read(adapter, _rules(), deadline=0., clock=lambda: 1.)
        self.assertEqual(adapter.frames, 0)

    def test_axis_then_diagonal_offsets_are_deduplicated(self):
        offsets = neighborhood_offsets(NeighborhoodLimits(steps=(1, .5), radius=1.5))
        self.assertEqual(len(offsets), 16)
        np.testing.assert_allclose(offsets[0], [1, 0])
        np.testing.assert_allclose(offsets[4], [1, 1])
        self.assertEqual(len({tuple(np.round(item, 6)) for item in offsets}), len(offsets))

    def test_radius_filters_diagonals(self):
        offsets = neighborhood_offsets(NeighborhoodLimits(steps=(1,), radius=1.0))
        self.assertEqual(len(offsets), 4)

    def test_candidate_poses_validate_center(self):
        poses = candidate_poses([10, 20], NeighborhoodLimits(steps=(1,), radius=1.1,
                                                              include_diagonals=False))
        self.assertEqual(len(poses), 4)
        np.testing.assert_allclose(poses[0], [11, 20])
        with self.assertRaises(ValueError):
            candidate_poses([1, np.inf])

    def test_score_and_best_use_all_regions(self):
        rules = _rules(tolerance=5)
        balanced = score_observation(["#666666"] * 3, rules, pose=[0, 0])
        one_region = score_observation(["#666666", "#FFFFFF", "#666666"], rules,
                                       pose=[1, 0])
        self.assertTrue(balanced["accepted"])
        self.assertFalse(one_region["accepted"])
        self.assertIs(retain_best(one_region, balanced), balanced)
        self.assertIs(retain_best(balanced, one_region), balanced)

    def test_rank_observations_is_deterministic_on_ties(self):
        rules = _rules(tolerance=5)
        first = score_observation(["#646464"] * 3, rules, pose=[0, 0])
        second = score_observation(["#646464"] * 3, rules, pose=[1, 1])
        self.assertEqual(rank_observations([second, first]), (second, first))


if __name__ == "__main__":
    unittest.main()
