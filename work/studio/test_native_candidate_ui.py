"""Real isolated Tk candidate events; never reads the game or sends input."""
import copy
import sys
import threading
import types
import unittest
from unittest.mock import patch

import app
import i18n
from search_overlay import SearchOverlay
import test_native_ui_hit_testing as hit_testing


RULES = [dict(enabled=True, exact=True, colors=['#000000', '#101010'], tolerance=0., priority=2),
         dict(enabled=True, exact=False, colors=['#000000'], tolerance=8., priority=1)]
MEASURED = dict(verified=True, screenshot_verified=True, accepted=True, target_exact=False,
                actual_colors=['#000000', '#010101'], actual_deltas=[0., .3],
                maximum=.3, average=.15, exact_matches=1, exact_total=1)


def candidates(batch='native-batch', current='best'):
    return dict(batch_id=batch, region_count=2, current_candidate_id=current,
                current_colors=['#000000', '#010101'], effective_deadline=999999999.,
                candidates=[dict(id='best', colors=['#000000', '#020202'], deltas=[0., .6],
                                 maximum=.6, average=.3, accepted=True, target_exact=False,
                                 source='current', current=current == 'best', predicted=True, available=True),
                            dict(id='other', colors=['#101010', '#151515'], deltas=[0., 7.],
                                 maximum=7., average=3.5, accepted=True, target_exact=False,
                                 source='local', current=current == 'other', predicted=True, available=True),
                            dict(id='unavailable', colors=['#323232', '#454545'], deltas=[20., 25.],
                                 maximum=25., average=22.5, accepted=False, target_exact=False,
                                 source='local', current=False, predicted=True, available=False)],
                observations={'best': copy.deepcopy(MEASURED)})


@unittest.skipUnless(sys.platform == 'win32', 'Native candidate Tk UI requires Windows')
class NativeCandidateUITests(unittest.TestCase):
    def setUp(self):
        self.helper = hit_testing.NativeUIHitTestingTests()
        self.addCleanup(self.helper.doCleanups)
        self.helper.setUp()
        self.ui = self.helper.ui
        self.ui.active_rules = copy.deepcopy(RULES)
        self.ui.active_region_count = 2
        self.ui.busy = True
        self.choices = []
        self.ui.runner = types.SimpleNamespace(stop=threading.Event(),
            choose_candidate=lambda batch, candidate: self.choices.append((batch, candidate)))
        self.ui.start.configure(state='disabled')
        self.ui.overlay = SearchOverlay(self.ui, self.ui.stop, self.ui.select_candidate)
        self.overlay = self.ui.overlay
        self.overlay.begin(RULES, passive=True)
        self.helper.pump(.03)

    def emit(self, kind, data):
        self.overlay.handle(kind, data)
        self.ui.handle_event(kind, data)
        self.helper.pump(.02)

    def labels(self, widget):
        result = []
        for child in widget.winfo_children():
            if isinstance(child, app.ct.CTkLabel):
                result.append(str(child.cget('text')))
            result.extend(self.labels(child))
        return result

    def test_no_candidate_button_stays_hidden_after_initial_scaling_and_reflow(self):
        self.assertFalse(self.ui.candidates_button.winfo_ismapped())
        for scaling in (1.25, 1.5, 1.):
            app.ct.set_widget_scaling(scaling)
            app.ct.set_window_scaling(scaling)
            self.ui.reflow(900)
            self.helper.pump(.03)
            self.assertFalse(self.ui.candidates_button.winfo_ismapped(),
                             f'No-candidate button reappeared at scaling {scaling}')
        data = candidates()
        data['candidates'] = []
        data['observations'] = {}
        data['current_candidate_id'] = None
        self.emit('native_candidates', data)
        self.assertFalse(self.ui.candidates_button.winfo_ismapped())

    def test_stop_hides_candidate_button_immediately_and_scaling_cannot_restore_it(self):
        self.emit('native_candidate_ready', candidates())
        self.assertTrue(self.ui.candidates_button.winfo_ismapped())
        self.ui.stop()
        self.helper.pump(.02)
        self.assertFalse(self.ui.candidates_button.winfo_ismapped())
        app.ct.set_widget_scaling(1.25)
        self.ui.reflow(900)
        self.helper.pump(.02)
        self.assertFalse(self.ui.candidates_button.winfo_ismapped())

    def test_new_run_clears_previous_candidate_button_before_worker_start(self):
        self.emit('native_candidate_ready', candidates())
        self.emit('native_candidate_closed', dict(batch_id='native-batch', reason='deadline'))
        self.emit('finished', {})
        self.assertTrue(self.ui.candidates_button.winfo_ismapped())
        with patch.object(app, 'build_runner', side_effect=RuntimeError('Isolated startup')):
            self.ui.go()
        app.ct.set_widget_scaling(1.25)
        self.ui.reflow(900)
        self.helper.pump(.02)
        self.assertIsNone(self.ui._native_candidate_batch)
        self.assertFalse(self.ui.candidates_button.winfo_ismapped())

    def test_ready_enables_only_affordable_alternatives_and_keeps_rank_order(self):
        data = candidates()
        self.emit('native_candidates', data)
        self.assertEqual(self.overlay.candidate_rows['other'].cget('state'), 'disabled')
        self.emit('native_candidate_ready', data)
        self.assertEqual(self.overlay.phase, 'choosing')
        self.assertFalse(self.overlay._native_policy['passive_input'])
        self.assertEqual(list(self.overlay.candidate_rows), ['best', 'other', 'unavailable'])
        self.assertEqual(self.overlay.candidate_rows['best'].cget('state'), 'disabled')
        self.assertEqual(self.overlay.candidate_rows['other'].cget('state'), 'normal')
        self.assertEqual(self.overlay.candidate_rows['unavailable'].cget('state'), 'disabled')
        self.overlay.choose('native-batch', 'unavailable')
        self.assertEqual(self.choices, [])
        texts = self.labels(self.overlay.results)
        self.assertTrue(any('#010101' in text for text in texts))
        self.assertFalse(any('区域 3' in text for text in texts))
        self.assertNotIn('正在定位', str(self.overlay.candidate_rows['best'].cget('text')))
        self.assertEqual(data['candidates'][0]['colors'], ['#000000', '#020202'])

    def test_selection_disables_candidate_clicks_but_keeps_overlay_chrome_reachable(self):
        self.emit('native_candidate_ready', candidates())
        self.overlay.candidate_rows['other'].invoke()
        self.assertFalse(self.overlay._native_policy['passive_input'])
        self.assertEqual(self.overlay.phase, 'positioning')
        self.overlay.choose('native-batch', 'other')
        self.assertEqual(self.choices, [('native-batch', 'other')])
        self.emit('native_candidate_selected', dict(batch_id='native-batch', candidate_id='other', status='positioning'))
        self.assertFalse(self.overlay._native_policy['passive_input'])
        self.assertEqual(self.overlay.phase, 'positioning')
        self.overlay.choose('native-batch', 'best')
        self.assertEqual(self.choices, [('native-batch', 'other')])

    def test_measured_worse_selection_updates_cards_without_saving_forecasts_or_history(self):
        before = self.ui.current_profile()
        self.emit('native_candidates', candidates())
        self.assertEqual(self.ui.history, [])
        self.emit('native_candidate_ready', candidates())
        self.assertIn('#010101', str(self.ui.cards[1].current.cget('text')))
        observed = dict(batch_id='native-batch', candidate_id='other', status='observed',
                        actual_colors=['#121212', '#171717'], actual_deltas=[1., 8.],
                        maximum=8., average=4.5, accepted=False, verified=True, screenshot_verified=True)
        self.emit('native_candidate_selected', observed)
        ready = candidates(current='other')
        ready['observations']['other'] = observed
        self.emit('native_candidate_ready', ready)
        self.assertIn('#121212', str(self.ui.cards[0].current.cget('text')))
        self.assertEqual(self.ui.history, [])
        self.assertEqual(self.ui.current_profile(), before)
        self.assertEqual(list(self.overlay.candidate_rows), ['best', 'other', 'unavailable'])
        self.assertEqual(self.overlay.candidate_rows['best'].cget('state'), 'normal')
        self.assertEqual(self.overlay.candidate_rows['other'].cget('state'), 'disabled')
        self.assertNotIn('恢复', str(self.ui.status.cget('text')))

    def test_completion_releases_main_controls_and_reopens_only_read_only_candidates(self):
        self.emit('native_candidate_ready', candidates())
        result = dict(MEASURED, rules=RULES, region_count=2, available_regions=[True, True, False],
                      stop_reason='target_observed', outcome='matched', actual_input_attempts=0)
        self.emit('native_result', result)
        self.emit('finished', {})
        self.assertEqual(self.overlay.state(), 'withdrawn')
        self.assertFalse(self.ui.busy)
        self.assertEqual(self.ui.start.cget('state'), 'normal')
        self.helper.hit(self.ui.cards[0].target_entry)
        self.assertTrue(self.ui.candidates_button.winfo_ismapped())
        self.ui.candidates_button.invoke()
        self.helper.pump(.03)
        self.assertEqual(self.overlay.state(), 'normal')
        self.assertEqual(self.overlay.phase, 'verified')
        self.assertIsNone(self.overlay.batch_id)
        self.assertFalse(self.overlay._native_policy['passive_input'])
        self.assertTrue(all(button.cget('state') == 'disabled' for button in self.overlay.candidate_rows.values()))
        self.overlay.choose('native-batch', 'other')
        self.assertEqual(self.choices, [])
        self.overlay.stop_button.invoke()
        self.assertEqual(self.overlay.state(), 'withdrawn')
        self.overlay.begin(RULES, passive=True)
        self.assertIsNone(self.overlay._candidate_data)
        self.assertIsNone(self.overlay.batch_id)
        self.assertEqual(len(self.ui.history), 1)

    def test_stale_ready_and_closed_events_cannot_reenable_previous_batch(self):
        self.emit('native_candidate_ready', candidates('new-batch'))
        self.emit('native_candidates', candidates('old-batch'))
        self.emit('native_candidate_ready', candidates('old-batch'))
        self.emit('native_candidate_closed', dict(batch_id='old-batch', reason='expired'))
        self.assertEqual(self.overlay.batch_id, 'new-batch')
        self.assertEqual(self.overlay.phase, 'choosing')
        self.emit('native_candidate_closed', dict(batch_id='new-batch', reason='expired'))
        self.assertIsNone(self.overlay.batch_id)
        self.assertEqual(self.overlay.phase, 'verified')
        self.overlay.choose('new-batch', 'other')
        self.assertEqual(self.choices, [])

    def test_unknown_terminal_colors_do_not_relabel_old_target_as_the_current_observation(self):
        self.emit('native_candidate_ready', candidates())
        result = dict(MEASURED, rules=RULES, region_count=2, actual_colors=['#ABABAB', '#BCBCBC'],
                      stop_reason='candidate_recovery_unconfirmed', outcome='stopped')
        self.emit('native_result', result)
        self.assertIsNone(self.overlay._candidate_data['current_candidate_id'])
        self.assertEqual(self.overlay._candidate_data['observations']['best']['actual_colors'],
                         ['#000000', '#010101'])

    def test_rejected_selection_reopens_choices_and_hides_internal_error_text(self):
        self.emit('native_candidate_ready', candidates())
        self.overlay.candidate_rows['other'].invoke()
        self.emit('native_candidate_selected', dict(batch_id='native-batch', candidate_id='other',
                  status='rejected', reason='candidate_compile_timeout'))
        self.assertEqual(self.overlay.phase, 'choosing')
        self.assertFalse(self.overlay._native_policy['passive_input'])
        self.assertEqual(self.overlay.candidate_rows['other'].cget('state'), 'normal')
        self.assertNotIn('candidate_compile_timeout', str(self.overlay.copy.cget('text')))
        self.assertNotIn('candidate_compile_timeout', str(self.ui.detail.cget('text')))
        self.overlay.candidate_rows['other'].invoke()
        self.assertEqual(self.choices, [('native-batch', 'other'), ('native-batch', 'other')])

    def test_restored_event_records_anchor_under_its_own_id_and_closing_uses_fresh_observation(self):
        self.emit('native_candidate_ready', candidates())
        self.emit('native_candidate_selected', dict(MEASURED, batch_id='native-batch', candidate_id='other',
                  current_candidate_id='best', status='restored'))
        self.assertEqual(set(self.overlay._candidate_data['observations']), {'best'})
        closed = dict(MEASURED, batch_id='native-batch', current_candidate_id=None,
                      current_colors=['#555555', '#666666'], actual_colors=['#555555', '#666666'], reason='deadline')
        self.emit('native_candidate_closed', closed)
        self.assertIn('#555555', str(self.ui.cards[0].current.cget('text')))
        self.assertIsNone(self.overlay._candidate_data['current_candidate_id'])
        self.assertEqual(self.overlay._candidate_data['observations']['best']['actual_colors'], ['#000000', '#010101'])

    def test_live_language_switch_translates_candidate_rows_and_read_only_controls(self):
        original = i18n.language
        self.addCleanup(i18n.set_language, original)
        self.emit('native_candidate_ready', candidates())
        for language in ('繁體中文', 'English', '简体中文'):
            i18n.set_language(language)
            self.helper.pump(.02)
            texts = '\n'.join(self.labels(self.overlay.results))
            self.assertIn('#010101', texts)
            self.assertEqual(str(self.overlay.heading.cget('text')), str(i18n.tr('本轮候选方案')))
            self.assertEqual(str(self.overlay.candidate_rows['other'].cget('text')),
                             str(i18n.tr('选择此方案')))
            if language == 'English':
                self.assertFalse(any('\u4e00' <= char <= '\u9fff' for char in texts), texts)
        self.emit('native_candidate_closed', dict(batch_id='native-batch', reason='expired'))
        self.emit('finished', {})
        self.ui.candidates_button.invoke()
        i18n.set_language('English')
        self.assertTrue(str(self.overlay.stop_button.cget('text')).startswith('Close '))


if __name__ == '__main__':
    unittest.main()
