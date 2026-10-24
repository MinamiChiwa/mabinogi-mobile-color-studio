import unittest
from itertools import chain, repeat
import numpy as np
import test_native_palette_actions as fixtures
from native_palette_scoring import score_native_pose
from native_target_seeds import target_seed_poses


class TargetSeedTests(unittest.TestCase):
    def setUp(self):
        f = fixtures.NativePaletteActionsTests()
        f.setUp()
        self.session = f.session

    def test_target_pixel_can_be_placed_at_enabled_picker(self):
        pixel = self.session['pixels'][0][123, 92]
        code = '#%02X%02X%02X' % tuple(pixel)
        rules = [dict(enabled=i == 0, exact=True, colors=[code], tolerance=0) for i in range(3)]
        result = target_seed_poses(self.session, rules, scales=(1.,), rotations_degrees=(0.,),
                                   pixels_per_region=4, period_offsets=((0, 0),))
        self.assertTrue(result['complete'])
        self.assertTrue(any(score_native_pose(self.session, p, rules)['predicted_accepted'] for p in result['poses']))
        self.assertTrue(all(seed['anchor_region'] == 0 for seed in result['seeds']))

    def test_count_limit_deadline_and_cancellation(self):
        rules = [dict(enabled=True, exact=True, colors=['#FFFFFF'], tolerance=0)] * 3
        result = target_seed_poses(self.session, rules, max_candidates=2)
        self.assertEqual(len(result['poses']), 2)
        self.assertEqual(result['stop_reason'], 'candidate_limit')
        ticks = chain([0.], repeat(2.))
        result = target_seed_poses(self.session, rules, time_budget_seconds=1, clock=lambda: next(ticks))
        self.assertEqual(result['poses'], [])
        self.assertEqual(result['stop_reason'], 'deadline')
        def stop():
            raise InterruptedError('F9')
        with self.assertRaises(InterruptedError):
            target_seed_poses(self.session, rules, check=stop)

    def test_invalid_scale_and_period_offsets_rejected(self):
        rules = [dict(enabled=True, exact=True, colors=['#FFFFFF'], tolerance=0)] * 3
        for kwargs in [dict(scales=(0.,)), dict(rotations_degrees=(np.inf,)),
                       dict(period_offsets=((.5, 0),)), dict(pixels_per_region=0)]:
            with self.assertRaises(ValueError):
                target_seed_poses(self.session, rules, **kwargs)

    def test_interpolated_target_missing_from_raw_pixels_gets_seed(self):
        pixels = np.array([[[0, 0, 0], [200, 200, 200]],
                           [[0, 0, 0], [200, 200, 200]]], np.uint8)
        session = dict(self.session, pixels=(pixels, pixels, pixels), color_preserve_ratio=0.)
        rules = [dict(enabled=i == 0, exact=True, colors=['#646464'], tolerance=0) for i in range(3)]
        raw = target_seed_poses(session, rules, pixels_per_region=4)
        self.assertFalse(any(score_native_pose(session, p, rules)['predicted_accepted'] for p in raw['poses']))
        sampled = target_seed_poses(session, rules, pixels_per_region=4, subpixel_fractions=(0., .5))
        self.assertTrue(any(score_native_pose(session, p, rules)['predicted_accepted'] for p in sampled['poses']))
        with self.assertRaises(ValueError):
            target_seed_poses(session, rules, subpixel_fractions=(1.,))


if __name__ == '__main__':
    unittest.main()
