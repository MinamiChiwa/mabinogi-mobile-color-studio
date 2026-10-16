"""Live color strips follow this run's readings, never an older result."""
import copy
import unittest
from unittest.mock import patch

import app
from result_history import describe_result
import test_native_ui_completion as completion


class LiveColorStripTests(unittest.TestCase):
    def setUp(self):
        self.ui = completion.NativeUICompletionTests().ui()
        self.ui.q.queue.clear()
        self.rules = copy.deepcopy(self.ui.active_rules)
        self.old = ['#FA8B28', '#A9685B', '#69B55B']
        self.ui.display_best(describe_result(self.old, self.rules))

    def strip(self, index):
        return self.ui.cards[index].best_label.configure.call_args.kwargs

    def assert_colors(self, colors):
        for index, color in enumerate(colors):
            self.assertIn(color, self.strip(index)['text'])
            self.assertEqual(self.strip(index)['fg_color'], color)

    def test_native_readbacks_refresh_strips_without_waiting_for_completed_result(self):
        with patch.object(app, 'save_result', side_effect=AssertionError('Live reads must not save history')):
            for colors in (['#FD9128', '#8E0126', '#51AF76'], ['#010203', '#8E0026', '#F3302D']):
                self.ui.handle_event('native_colors', dict(colors=colors, screenshot_verified=False))
                self.assert_colors(colors)
                for card, color in zip(self.ui.cards, colors):
                    self.assertIn(color, card.current.configure.call_args.kwargs['text'])

    def test_screenshot_readbacks_and_refinement_show_current_trial_not_retained_color(self):
        colors = ['#010101', '#8E0026', '#E62C2B']
        self.ui.handle_event('scene', dict(colors=colors, seconds=61))
        self.assert_colors(colors)
        colors = ['#020202', '#8F0026', '#E72C2B']
        self.ui.handle_event('screenshot_progress', dict(stage='refinement', refinement_status='trial',
            current_colors=colors, current_deltas=[1., 58., 20.], verified=True, screenshot_verified=True,
            retained_colors=self.old, retained_deltas=[11., 74., 58.]))
        self.assert_colors(colors)
        self.assertIn('尚未替换', str(self.ui.set_detail.call_args.args[0]))

    def test_unconfirmed_end_uses_this_runs_last_measurement_without_saving_success(self):
        colors = ['#FD9128', '#8E0126', '#51AF76']
        with patch.object(app, 'save_result', side_effect=AssertionError('Historical reads are not current success')):
            self.ui.handle_event('native_result', dict(stop_reason='palette_ended', verified=False,
                actual_colors=[None]*3, last_verified_colors=colors,
                last_verified_deltas=[11.46, 58., 70.4], last_verified_screenshot=True))
        self.assert_colors(colors)
        for card in self.ui.cards:
            self.assertIn('当前未确认', str(card.current.configure.call_args.kwargs['text']))

    def test_missing_reading_clears_old_strip_instead_of_preserving_another_run(self):
        self.ui.handle_event('native_result', dict(stop_reason='interrupted', verified=False,
            actual_colors=[None]*3))
        for index in range(3):
            self.assertNotIn(self.old[index], self.strip(index)['text'])
            self.assertEqual(self.strip(index)['fg_color'], '#28364A')

    def test_history_write_failure_cannot_block_current_color_strip(self):
        colors = ['#010101', '#8E0026', '#E62C2B']
        with patch.object(app, 'save_result', side_effect=OSError('Read-only history directory')):
            self.ui.handle_event('native_result', dict(stop_reason='compromise_observed', verified=True,
                actual_colors=colors, accepted=False, outcome='compromise'))
        self.assert_colors(colors)


if __name__ == '__main__':
    unittest.main()
