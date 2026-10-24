import unittest
from itertools import chain, repeat
from unittest.mock import patch
import test_native_palette_actions as action_tests
from native_palette_action_search import search_native_actions


class NativeActionSearchTests(unittest.TestCase):
    def setUp(self):
        fixture = action_tests.NativePaletteActionsTests()
        fixture.setUp()
        self.fixture = fixture

    def run_search(self, poses, **kwargs):
        f = self.fixture
        return search_native_actions(f.session, poses, f.reference, f.board, f.markers,
                                     f.rules, now=0, deadline=100, **kwargs)

    def test_real_compiler_deduplicates_identical_zero_endpoints(self):
        f = self.fixture
        result = self.run_search([f.reference, f.reference, dict(f.reference, position=[5.4 / 530, 0.])])
        self.assertEqual(result['evaluated'], 3)
        self.assertEqual(result['unique_endpoints'], 2)
        self.assertEqual(result['duplicate_endpoints'], 1)
        self.assertTrue(result['candidates'][0]['planned_predicted_accepted'])
        self.assertFalse(result['candidates'][0]['execution_verified'])

    def test_ranking_uses_endpoint_instead_of_proposal_and_rejects_budget(self):
        def row(proposal_rank, planned_rank, allowed=True, endpoint=0, needed=1):
            return dict(plan_allowed=allowed, proposal_prediction={'rank': proposal_rank},
                        planned_prediction={'rank': planned_rank}, budget={'planned_pose': [[1, 0, endpoint], [0, 1, 0]], 'needed': needed},
                        planned_predicted_accepted=False)
        mocked = [row((False, 0), (True, 20)), row((True, 10), (True, 2), endpoint=1),
                  row((False, 0), (False, 0), allowed=False, endpoint=2)]
        with patch('native_palette_action_search.assess_native_action', side_effect=mocked):
            result = self.run_search([self.fixture.reference] * 3)
        self.assertEqual([r['candidate_index'] for r in result['candidates']], [1, 0])
        self.assertEqual(result['rejected_budget'], 1)

    def test_duplicate_endpoint_keeps_less_expensive_route(self):
        base = dict(plan_allowed=True, proposal_prediction={}, planned_prediction={'rank': (False, 0)},
                    planned_predicted_accepted=True)
        rows = [dict(base, budget={'planned_pose': [[1, 0, 0], [0, 1, 0]], 'needed': n}) for n in (5, 2)]
        with patch('native_palette_action_search.assess_native_action', side_effect=rows):
            result = self.run_search([self.fixture.reference] * 2)
        self.assertEqual(result['candidates'][0]['candidate_index'], 1)

    def test_limits_deadline_and_cancel(self):
        result = self.run_search([self.fixture.reference] * 3, max_candidates=1)
        self.assertEqual(result['stop_reason'], 'candidate_limit')
        self.assertEqual(result['evaluated'], 1)
        ticks = chain([0.], repeat(2.))
        result = self.run_search([self.fixture.reference], time_budget_seconds=1, clock=lambda: next(ticks))
        self.assertEqual(result['evaluated'], 0)
        self.assertEqual(result['stop_reason'], 'deadline')
        def stop():
            raise InterruptedError('F9')
        with self.assertRaises(InterruptedError):
            self.run_search([self.fixture.reference], check=stop)

    def test_completed_search_rechecks_action_time_remaining(self):
        elapsed = [0.]
        def assess(*args, **kwargs):
            elapsed[0] = 99.
            return dict(plan_allowed=True, planned_prediction={'rank': (False, 0)},
                        budget={'planned_pose': [[1, 0, 0], [0, 1, 0]], 'needed': 5},
                        planned_predicted_accepted=True)
        with patch('native_palette_action_search.assess_native_action', side_effect=assess):
            result = self.run_search([self.fixture.reference], time_budget_seconds=100,
                                     clock=lambda: elapsed[0])
        self.assertEqual(result['candidates'], [])
        self.assertEqual(result['expired_after_search'], 1)


if __name__ == '__main__':
    unittest.main()
