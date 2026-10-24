import unittest
from itertools import chain, repeat
from unittest.mock import patch
import test_native_palette_actions as fixtures
from native_palette_search import PoseGrid
from native_target_pipeline import search_target_pipeline


class TargetPipelineTests(unittest.TestCase):
    def setUp(self):
        f = fixtures.NativePaletteActionsTests()
        f.setUp()
        self.f = f
        self.grid = PoseGrid((-.01, .01), (-.01, .01), 3, 3, (1.,), (0.,))

    def test_all_stages_share_budget_and_return_endpoint_refinement(self):
        f = self.f
        result = search_target_pipeline(f.session, self.grid, f.reference, f.board, f.markers,
                                        f.rules, now=0, deadline=100, time_budget_seconds=10,
                                        seed_budget=.1, coarse_budget=.1, endpoint_budget=.1,
                                        shortlist=3, refine=False)
        self.assertIn('seed', result['stages'])
        self.assertIn('coarse', result['stages'])
        self.assertIn('endpoint', result['stages'])
        self.assertFalse(result['execution_verified'])
        self.assertLessEqual(result['elapsed_seconds'], 10)
        self.assertEqual(result['stop_reason'], 'completed')

    def test_deadline_stops_before_later_stages(self):
        f = self.f
        ticks = chain([0.], repeat(2.))
        result = search_target_pipeline(f.session, self.grid, f.reference, f.board, f.markers,
                                        f.rules, now=0, deadline=1, time_budget_seconds=1,
                                        seed_budget=.8, coarse_budget=.1, endpoint_budget=.1,
                                        clock=lambda: next(ticks))
        self.assertEqual(result['stop_reason'], 'deadline')
        self.assertIsNone(result['stages']['coarse'])
        self.assertIsNone(result['stages']['endpoint'])

    def test_cancel_propagates_and_invalid_reserves_reject(self):
        f = self.f
        with self.assertRaises(ValueError):
            search_target_pipeline(f.session, self.grid, f.reference, f.board, f.markers,
                                   f.rules, now=0, deadline=10, time_budget_seconds=1,
                                   seed_budget=.8, coarse_budget=.3, endpoint_budget=.1)
        def stop():
            raise InterruptedError('F9')
        with self.assertRaises(InterruptedError):
            search_target_pipeline(f.session, self.grid, f.reference, f.board, f.markers,
                                   f.rules, now=0, deadline=10, time_budget_seconds=1,
                                   check=stop)

    def test_grid_fallback_works_when_no_target_seeds(self):
        f = self.f
        with patch('native_target_pipeline.target_seed_poses', return_value={'poses': [], 'generated': 0,
                                                                              'elapsed_seconds': 0, 'stop_reason': 'seeds_exhausted'}):
            result = search_target_pipeline(f.session, self.grid, f.reference, f.board, f.markers,
                                            f.rules, now=0, deadline=10, time_budget_seconds=1,
                                            seed_budget=.1, coarse_budget=.1, endpoint_budget=.1,
                                            refine=False)
        self.assertEqual(result['capture_id'], f.session['capture_id'])

    def test_time_spent_in_refinement_rejects_unaffordable_old_route(self):
        f = self.f
        ticks = [0.]
        row = dict(capture_id=f.session['capture_id'], budget={'needed': 4},
                   planned_prediction={'rank': (False, 0)})
        def refine(*args, **kwargs):
            ticks[0] = 7.
            return {'candidates': [row], 'stop_reason': 'layers_exhausted'}
        with patch('native_target_pipeline.target_seed_poses', return_value={'poses': [], 'generated': 0}), \
             patch('native_target_pipeline.score_native_pose', return_value={'rank': (False, 0), 'native_pose': f.reference}), \
             patch('native_target_pipeline.search_native_actions', return_value={'candidates': [row]}), \
             patch('native_target_pipeline.refine_action_endpoints', side_effect=refine):
            result = search_target_pipeline(f.session, self.grid, f.reference, f.board, f.markers,
                                            f.rules, now=0, deadline=10, time_budget_seconds=10,
                                            clock=lambda: ticks[0])
        self.assertEqual(result['candidates'], [])
        self.assertEqual(result['execution_seconds_remaining'], 3.)


if __name__ == '__main__':
    unittest.main()
