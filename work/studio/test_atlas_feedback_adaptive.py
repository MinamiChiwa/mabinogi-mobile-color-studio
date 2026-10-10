import unittest

import numpy as np

from atlas_execution import _feedback_refine


class _FeedbackAdapter:
    """Tiny measured adapter for the bounded HEX feedback loop."""

    def __init__(self, colors):
        self.pose = np.zeros(2, dtype=float)
        self.colors = colors
        self.moves = []

    def check(self):
        return None

    def pause(self, _seconds):
        return None

    def capture(self):
        return self.pose.copy()

    def motion(self, before, after):
        before = np.asarray(before, dtype=float)
        after = np.asarray(after, dtype=float)
        delta = after - before
        return {
            "matrix": [[1.0, 0.0, float(delta[0])],
                       [0.0, 1.0, float(delta[1])]],
            "scale": 1.0,
            "angle": 0.0,
        }

    def perform_gesture(self, gesture):
        dx, dy = gesture.translation
        self.moves.append((int(dx), int(dy)))
        self.pose += (float(dx), float(dy))

    def read_codes(self, frame):
        key = tuple(np.rint(np.asarray(frame, dtype=float)).astype(int))
        return list(self.colors.get(key, ["#000000"] * 3))


class _SequencedFeedbackAdapter(_FeedbackAdapter):
    """Return a scripted OCR stream, independent of the measured pose."""

    def __init__(self, values):
        super().__init__({})
        self.values = [list(value) for value in values]

    def read_codes(self, _frame):
        if not self.values:
            return ["#000000"] * 3
        return self.values.pop(0)


class AdaptiveFeedbackTests(unittest.TestCase):
    rules = [
        {"enabled": True, "colors": ["#112233"], "exact": False, "tolerance": 0},
        {"enabled": True, "colors": ["#112233"], "exact": False, "tolerance": 0},
        {"enabled": True, "colors": ["#112233"], "exact": False, "tolerance": 0},
    ]

    def _run(self, adapter, **kwargs):
        events = []
        result = _feedback_refine(
            adapter,
            {"id": 0},
            np.eye(3),
            adapter.capture(),
            ["#000000"] * 3,
            self.rules,
            np.asarray(((10, 10), (20, 10), (30, 10)), dtype=float),
            (0, 0, 100, 100),
            100.0,
            lambda kind, data: events.append((kind, data)),
            clock=lambda: 0.0,
            return_guard=getattr(adapter, "return_guard", None),
            **kwargs,
        )
        return result, events

    def test_first_probe_miss_stops_before_second_probe(self):
        # The first (+1, 0) sample is worse.  The historical best is restored,
        # but the next axis is never probed.
        adapter = _FeedbackAdapter({
            (0, 0): ["#000000"] * 3,
            (1, 0): ["#ffffff"] * 3,
            (-1, 0): ["#112233"] * 3,
        })
        result, events = self._run(adapter)
        feedback = [data for kind, data in events if kind == "atlas_hex_feedback"]
        self.assertEqual([row["step"] for row in feedback], [1])
        self.assertEqual(adapter.moves, [(1, 0), (-1, 0)])
        self.assertEqual(result[-1], "no_improvement")

    def test_second_probe_is_used_only_after_first_improvement(self):
        adapter = _FeedbackAdapter({
            (0, 0): ["#000000"] * 3,
            (1, 0): ["#102030"] * 3,
            (-1, 0): ["#112232"] * 3,
        })
        result, events = self._run(adapter)
        feedback = [data for kind, data in events if kind == "atlas_hex_feedback"]
        self.assertEqual([row["step"] for row in feedback], [1, 2])
        self.assertEqual(adapter.moves, [(1, 0), (-2, 0)])
        self.assertTrue(result[4])

    def test_max_probes_can_be_lowered_without_disabling_restore(self):
        adapter = _FeedbackAdapter({
            (0, 0): ["#000000"] * 3,
            (1, 0): ["#102030"] * 3,
            (-1, 0): ["#112232"] * 3,
        })
        result, events = self._run(adapter, max_probes=1)
        feedback = [data for kind, data in events if kind == "atlas_hex_feedback"]
        self.assertEqual([row["step"] for row in feedback], [1])
        # The one allowed probe became the best sample, so no restore input
        # is needed when the caller lowers the probe budget explicitly.
        self.assertEqual(adapter.moves, [(1, 0)])
        self.assertTrue(result[4])

    def test_unstable_probe_keeps_registered_pose_for_restore(self):
        """A failed HEX read must not make an emitted drag look reversible.

        The first probe moves the game to (+1, 0), then returns two different
        HEX frames.  The implementation must retain that registered pose and
        spend the restore action to get back to the historical best.  Before
        this regression fix ``current_actual`` stayed at the pre-action pose,
        so the restore was skipped while the adapter remained displaced.
        """
        adapter = _SequencedFeedbackAdapter([
            ["#102030"] * 3,
            ["#102031"] * 3,
            ["#000000"] * 3,
            ["#000000"] * 3,
        ])
        result, events = self._run(adapter, max_probes=1)
        self.assertEqual(adapter.moves, [(1, 0), (-1, 0)])
        np.testing.assert_allclose(adapter.pose, [0, 0])
        np.testing.assert_allclose(result[0][:2, 2], [0, 0])
        self.assertTrue(result[4])
        self.assertIn("HEX changed", result[-1])

    def test_blocked_restore_cannot_publish_pre_action_hex(self):
        """If the restore reserve is denied, colors stay explicitly unknown."""
        adapter = _SequencedFeedbackAdapter([
            ["#102030"] * 3,
            ["#102031"] * 3,
        ])
        calls = []

        def guard(_actual, _upcoming, **_kwargs):
            calls.append(True)
            return {"allowed": len(calls) == 1}

        adapter.return_guard = guard
        result, _events = self._run(adapter, max_probes=1)
        self.assertEqual(adapter.moves, [(1, 0)])
        self.assertFalse(result[4])
        self.assertEqual(result[2], [None, None, None])
        np.testing.assert_allclose(result[0][:2, 2], [1, 0])


if __name__ == "__main__":
    unittest.main()
