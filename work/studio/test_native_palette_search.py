from test_support import read_local_fixture_text
from test_support import load_local_palette_session
import json
import unittest
from pathlib import Path
from native_palette_scoring import load_session, score_native_pose, rank_native_poses
from native_palette_search import PoseGrid, search_pose_grid


class NativePaletteSearchTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).parent / 'fixtures' / 'native_palette'
        names = json.loads(read_local_fixture_text(root / 'manifest.json'))['snapshots']
        self.session = load_local_palette_session(root / names[1])
        self.rules = [dict(enabled=True, exact=True, colors=['#000000'], tolerance=0) for _ in range(3)]

    def test_grid_recovers_client_initial_hex_without_seed(self):
        self.rules[0]['colors'] = ['#D7856D']
        self.rules[1]['colors'] = ['#D0D2B4']
        self.rules[2]['colors'] = ['#6D8354']
        grid = PoseGrid((-.01, .01), (-.01, .01), 3, 3, (1.,), (0.,))
        result = search_pose_grid(self.session, grid, self.rules, top_k=2)
        self.assertEqual(result['evaluated'], 9)
        self.assertEqual(result['stop_reason'], 'grid_exhausted')
        self.assertTrue(result['grid_complete'])
        self.assertTrue(result['candidates'][0]['predicted_accepted'])
        self.assertEqual(result['candidates'][0]['native_pose']['position'], [0., 0.])
        self.assertFalse(result['candidates'][0]['verified'])
        self.assertEqual(len(result['candidates']), 2)

    def test_candidate_limit_does_not_claim_complete(self):
        grid = PoseGrid((-.1, .1), (-.1, .1), 3, 3, (1.,), (0.,))
        result = search_pose_grid(self.session, grid, self.rules, max_candidates=3)
        self.assertEqual(result['evaluated'], 3)
        self.assertEqual(result['planned_candidates'], 9)
        self.assertFalse(result['grid_complete'])
        self.assertEqual(result['stop_reason'], 'candidate_limit')

    def test_deadline_does_not_score_after_expiry(self):
        grid = PoseGrid((0., 0.), (0., 0.), 1, 1, (1.,), (0.,))
        ticks = iter([0., 1., 1., 1.])
        result = search_pose_grid(self.session, grid, self.rules, time_budget_seconds=.5,
                                  clock=lambda: next(ticks))
        self.assertEqual(result['evaluated'], 0)
        self.assertEqual(result['candidates'], [])
        self.assertEqual(result['stop_reason'], 'deadline')

    def test_guard_and_invalid_grid(self):
        for args in [((1., -1.), (0., 1.), 2, 2, (1.,), (0.,)),
                     ((0., 1.), (0., 1.), 0, 2, (1.,), (0.,)),
                     ((0., 1.), (0., 1.), 2, 2, (0.,), (0.,))]:
            with self.assertRaises(ValueError):
                PoseGrid(*args)
        def stop():
            raise InterruptedError('F9')
        grid = PoseGrid((0., 0.), (0., 0.), 1, 1, (1.,), (0.,))
        with self.assertRaises(InterruptedError):
            search_pose_grid(self.session, grid, self.rules, check=stop)

    def test_retained_top_k_matches_full_sort_with_scale_rotation(self):
        grid = PoseGrid((-.01, .01), (-.01, .01), 2, 2, (.99, 1.), (-2., 2.))
        expected = rank_native_poses(self.session, grid.poses(), self.rules)
        result = search_pose_grid(self.session, grid, self.rules, top_k=3)
        self.assertEqual(result['planned_candidates'], 16)
        self.assertEqual([r['candidate_index'] for r in result['candidates']],
                         [r['candidate_index'] for r in expected[:3]])


if __name__ == '__main__':
    unittest.main()
