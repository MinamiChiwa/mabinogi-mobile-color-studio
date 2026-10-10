import unittest
from unittest.mock import patch
import test_native_action_search as fixtures
from native_palette_search import PoseGrid
from native_palette_pipeline import search_native_pipeline


class PipelineTests(unittest.TestCase):
    def setUp(self):
        test = fixtures.NativeActionSearchTests()
        test.setUp()
        self.f = test.fixture

    def test_shortlist_limits_compilation_and_preserves_initial_exact(self):
        f = self.f
        grid = PoseGrid((-.01, .01), (-.01, .01), 3, 3, (1.,), (0.,))
        result = search_native_pipeline(f.session, grid, f.reference, f.board, f.markers,
                                        f.rules, now=0, deadline=100, shortlist=3)
        self.assertEqual(result['coarse']['evaluated'], 9)
        self.assertEqual(result['actions']['evaluated'], 3)
        self.assertTrue(result['actions']['candidates'][0]['planned_predicted_accepted'])
        self.assertIn('shortlist', result['optimality'])

    def test_coarse_budget_can_leave_no_time_for_actions(self):
        f = self.f
        def coarse(*args, **kwargs):
            ticks[0] = 2.
            return dict(candidates=[], evaluated=0, stop_reason='deadline')
        ticks = [0.]
        grid = PoseGrid((0, 0), (0, 0), 1, 1, (1.,), (0.,))
        with patch('native_palette_pipeline.search_pose_grid', side_effect=coarse):
            result = search_native_pipeline(f.session, grid, f.reference, f.board, f.markers,
                                            f.rules, now=0, deadline=100, time_budget_seconds=1,
                                            clock=lambda: ticks[0])
        self.assertIsNone(result['actions'])
        self.assertEqual(result['stop_reason'], 'search_deadline')

    def test_coarse_stage_reserves_time_for_endpoint_compilation(self):
        f = self.f
        grid = PoseGrid((0, 0), (0, 0), 1, 1, (1.,), (0.,))
        with patch('native_palette_pipeline.search_pose_grid', return_value={'candidates': []}) as coarse:
            result = search_native_pipeline(f.session, grid, f.reference, f.board, f.markers,
                                            f.rules, now=0, deadline=100, time_budget_seconds=10,
                                            action_reserve_seconds=3, clock=lambda: 0)
        self.assertEqual(coarse.call_args.kwargs['time_budget_seconds'], 7)
        self.assertEqual(result['action_reserve_seconds'], 3)

    def test_reserve_cannot_consume_entire_search_budget(self):
        f = self.f
        grid = PoseGrid((0, 0), (0, 0), 1, 1, (1.,), (0.,))
        with self.assertRaises(ValueError):
            search_native_pipeline(f.session, grid, f.reference, f.board, f.markers,
                                   f.rules, now=0, deadline=100, time_budget_seconds=1,
                                   action_reserve_seconds=1)


if __name__ == '__main__':
    unittest.main()
