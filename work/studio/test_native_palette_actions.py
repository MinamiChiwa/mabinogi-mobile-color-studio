from test_support import read_local_fixture_text
from test_support import load_local_palette_session
import json
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from native_palette_scoring import load_session, score_native_pose
from native_palette_pose import board_to_native
from native_palette_actions import assess_native_action


class NativePaletteActionsTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).parent / 'fixtures' / 'native_palette'
        name = json.loads(read_local_fixture_text(root / 'manifest.json'))['snapshots'][1]
        self.session = load_local_palette_session(root / name)
        self.reference = self.session['initial_pose']
        self.board = [757, 428, 1287, 958]
        self.markers = [[757 + u * 530, 428 + (1 - v) * 530] for u, v in self.session['picker_uv']]
        self.rules = [dict(enabled=True, exact=True, colors=[c], tolerance=0)
                      for c in ['#D7856D', '#D0D2B4', '#6D8354']]

    def test_zero_move_keeps_prediction_and_never_certifies_execution(self):
        result = assess_native_action(self.session, self.reference, self.reference,
                                      self.board, self.markers, self.rules, now=0, deadline=100)
        self.assertTrue(result['plan_allowed'])
        self.assertTrue(result['planned_predicted_accepted'])
        self.assertFalse(result['execution_verified'])
        self.assertFalse(result['game_response_verified'])
        self.assertNotIn('accepted', result)

    def test_real_budget_rounds_translation_and_rescores_endpoint(self):
        target = dict(self.reference, position=[5.4 / 530, 0.])
        result = assess_native_action(self.session, target, self.reference,
                                      self.board, self.markers, self.rules, now=0, deadline=100)
        np.testing.assert_allclose(result['budget']['planned_pose'], [[1, 0, 5], [0, 1, 0]], atol=1e-5)
        endpoint = board_to_native(result['budget']['planned_pose'], self.reference, self.board)
        self.assertEqual(result['planned_prediction']['colors'], score_native_pose(self.session, endpoint, self.rules)['colors'])

    def test_plan_can_be_allowed_while_endpoint_colors_fail(self):
        budget = dict(allowed=True, reason='ok', planned_pose=[[1, 0, 20], [0, 1, 10]], game_response_verified=False)
        with patch('native_palette_actions.reposition_budget', return_value=budget):
            result = assess_native_action(self.session, self.reference, self.reference,
                                          self.board, self.markers, self.rules, now=0, deadline=100)
        self.assertTrue(result['proposal_prediction']['predicted_accepted'])
        self.assertTrue(result['plan_allowed'])
        self.assertFalse(result['planned_predicted_accepted'])
        self.assertFalse(result['eligible_for_live_validation'])

    def test_expired_budget_has_no_endpoint_and_cancellation_propagates(self):
        result = assess_native_action(self.session, self.reference, self.reference,
                                      self.board, self.markers, self.rules, now=100, deadline=100)
        self.assertFalse(result['plan_allowed'])
        self.assertIsNone(result['planned_prediction'])
        def stop():
            raise InterruptedError('F9')
        with self.assertRaises(InterruptedError):
            assess_native_action(self.session, self.reference, self.reference,
                                 self.board, self.markers, self.rules, now=0, deadline=100, check=stop)


if __name__ == '__main__':
    unittest.main()
