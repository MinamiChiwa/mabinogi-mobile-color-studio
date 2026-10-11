"""Isolated desktop retry controls; no process reads or game input."""
import copy
import sys
import threading
from types import SimpleNamespace
import unittest

from search_overlay import SearchOverlay
import test_native_ui_hit_testing as hit_testing

RULES=[dict(enabled=True,exact=True,colors=['#000000'],tolerance=0.,priority=i+1) for i in range(3)]


@unittest.skipUnless(sys.platform=='win32','Retry UI requires Windows')
class NativeRetryUITests(unittest.TestCase):
    def setUp(self):
        import app
        from unittest.mock import patch
        language=patch.object(app.i18n,'language','简体中文');language.start();self.addCleanup(language.stop)
        self.helper=hit_testing.NativeUIHitTestingTests();self.helper.setUp()
        self.addCleanup(self.helper.doCleanups)
        self.ui=self.helper.ui;self.requests=[]
        self.ui.busy=True;self.ui.search_strategy.set('native')
        self.ui.runner=SimpleNamespace(stop=threading.Event(),request_retry=lambda:self.requests.append(True))
        self.ui.overlay=SearchOverlay(self.ui,self.ui.stop,self.ui.select_candidate)
        self.ui.overlay.begin(copy.deepcopy(RULES),passive=True)
        self.helper.pump(.02)
    def emit(self,kind,data):
        self.ui.overlay.handle(kind,data);self.ui.handle_event(kind,data);self.helper.pump(.02)
    def test_retry_button_and_f7_share_request_bridge_and_never_change_saved_targets(self):
        before=self.ui.current_profile()
        self.emit('native_retry_available',dict(enabled=True,effective_deadline=999999999.))
        button=getattr(self.ui.overlay,'retry_button',None)
        self.assertIsNotNone(button,'Native runs require a retry button, not predicted alternatives')
        self.assertEqual(button.cget('state'),'normal')
        button.invoke();self.assertEqual(self.requests,[True])
        self.emit('native_retry_reset',dict(status='searching',epoch=1))
        self.emit('native_retry_available',dict(enabled=True,effective_deadline=999999999.))
        self.ui.handle_event('hotkey',dict(id=3))
        self.assertEqual(len(self.requests),2)
        self.assertFalse(self.ui.runner.stop.is_set())
        self.assertEqual(self.ui.current_profile(),before)

    def test_retry_button_reactivates_bound_game_before_request(self):
        import app
        from unittest.mock import patch
        self.ui.selected_window=SimpleNamespace(hwnd=1234,pid=88,title='game')
        self.emit('native_retry_available',dict(enabled=True,effective_deadline=999999999.))
        button=getattr(self.ui.overlay,'retry_button',None)
        with patch.object(app,'activate_target_window',create=True) as activate:
            button.invoke()
        activate.assert_called_once_with(self.ui.selected_window)
        self.assertEqual(self.requests,[True])

    def test_failed_activation_keeps_retry_available_instead_of_stranding_overlay(self):
        import app
        from unittest.mock import patch
        self.ui._bound_target=app.WindowTarget(50,123,'Game')
        self.emit('native_retry_available',dict(enabled=True))
        with patch.object(app,'activate_target_window',return_value=False):
            self.ui.overlay.retry_button.invoke()
        self.assertEqual(self.requests,[])
        self.assertEqual(self.ui.overlay.retry_button.cget('state'),'normal')
        self.assertFalse(self.ui.overlay._retry_pending)
    def test_retry_rejected_or_preparing_cannot_issue_duplicate_or_partial_requests(self):
        self.emit('native_retry_available',dict(enabled=True,effective_deadline=999999999.))
        button=getattr(self.ui.overlay,'retry_button',None)
        self.assertIsNotNone(button)
        button.invoke();button.invoke()
        self.assertEqual(self.requests,[True])
        self.emit('native_retry_reset',dict(status='zooming',epoch=1))
        self.ui.handle_event('hotkey',dict(id=3))
        self.assertEqual(self.requests,[True])
        self.emit('native_retry_available',dict(enabled=False,reason='insufficient_retry_time'))
        self.assertEqual(button.cget('state'),'disabled')
    def test_native_prediction_events_do_not_create_candidate_widgets(self):
        self.emit('native_retry_available',dict(enabled=True))
        self.emit('native_candidates',dict(batch_id='obsolete',candidates=[dict(id='x',colors=['#121212']*3,
            deltas=[1.]*3,maximum=1.,average=1.,accepted=False)],current_candidate_id=None))
        self.assertEqual(self.ui.overlay.candidate_rows,{})
        self.assertIsNone(self.ui.overlay._candidate_data)
    def test_unavailable_and_rejected_retry_show_actual_cause_in_both_surfaces(self):
        for reason,expected in (('insufficient_retry_actions','操作'),('unsupported_retry_settings','缩小')):
            for kind,fields in (('native_retry_available',dict(enabled=False,waiting_for_retry=True)),
                    ('native_retry_reset',dict(status='rejected'))):
                with self.subTest(reason=reason,kind=kind):
                    self.emit(kind,dict(fields,reason=reason))
                    for widget in (self.ui.detail,self.ui.overlay.copy):
                        body=str(widget.cget('text'))
                        self.assertIn(expected,body)
                        self.assertNotIn('时间不足',body)
                    self.assertEqual(self.ui.overlay.retry_button.cget('state'),'disabled')
    def test_finish_hides_retry_surface_and_releases_main_window_controls(self):
        self.emit('native_retry_available',dict(enabled=True))
        self.emit('finished',{})
        self.assertFalse(self.ui.busy)
        self.assertEqual(self.ui.start.cget('state'),'normal')
        self.assertEqual(self.ui.overlay.state(),'withdrawn')
        self.ui.handle_event('hotkey',dict(id=3))
        self.assertEqual(self.requests,[])

    def test_refinement_shows_measured_results_without_resetting_progress_or_blocking_stop(self):
        import app
        from unittest.mock import patch
        overlay=self.ui.overlay
        for scale,colors,deltas in ((1.,['#FFFFFF','#FFFFFF','#EBEEDC'],[0.,0.,11.45]),
                                    (1.5,['#FFFFFF','#EBEEDC'],[0.,11.45])):
            app.ct.set_widget_scaling(scale);app.ct.set_window_scaling(scale)
            event=dict(stage='refinement',current_colors=colors,current_deltas=deltas,
                       verified=True,screenshot_verified=True,examined=14527)
            self.emit('native_progress',event)
            for label in (self.ui.detail,overlay.copy):
                body=str(label.cget('text'))
                self.assertIn('当前配色 · 游戏实测',body)
                self.assertIn('#EBEEDC · ΔE 11.45',body)
                self.assertNotIn('14527',body)
                self.assertEqual('区域 3' in body,len(colors)==3)
            self.assertIn(colors[0],str(self.ui.cards[0].current.cget('text')))
            # Finish the initial stage/layout frame before counting redraws
            # caused by repeated identical progress events.
            self.helper.pump(.1)
            stage_started=overlay._stage_started
            with patch.object(overlay,'schedule_surface_resize',wraps=overlay.schedule_surface_resize) as resize:
                for n in range(3):
                    repeated=dict(event,examined=15000+n)
                    overlay.handle('native_progress',repeated);self.ui.handle_event('native_progress',repeated)
                resize.assert_not_called()
            self.assertEqual(overlay._stage_started,stage_started)
            self.assertEqual(overlay.candidate_rows,{})
            self.assertIsNotNone(overlay._heartbeat_job)
            overlay.toggle_collapse();self.helper.pump(.03)
            self.helper.hit(overlay.stop_button)
            overlay.toggle_collapse();self.helper.pump(.03)
            self.emit('native_progress',dict(stage='position'))
            self.assertNotIn('当前配色 · 游戏实测',str(overlay.copy.cget('text')))
            self.assertFalse(overlay._refinement_status)
        self.ui.handle_event('hotkey',dict(id=2))
        self.assertTrue(self.ui.runner.stop.is_set())
        self.assertEqual(overlay.state(),'withdrawn')
        self.assertEqual(self.helper.errors,[])


if __name__=='__main__':unittest.main()
