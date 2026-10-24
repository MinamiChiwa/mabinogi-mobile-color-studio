"""A failed event presentation must not strand the native completion event."""
import queue
import threading
import types
import tempfile
import weakref
import gc
import unittest
from unittest.mock import Mock,patch
import app
from search_overlay import SearchOverlay


RESULT=dict(stop_reason='compromise_observed',outcome='compromise',accepted=False,verified=True,
    target_exact=False,actual_colors=['#241410','#1D1000','#B360B5'],
    actual_deltas=[12.441825866699219,11.0386962890625,None],
    best_actual_colors=['#241410','#1D1000','#B360B5'],
    maximum=12.441825866699219,average=11.74026107788086)
RULES=[dict(enabled=True,exact=True,colors=['#000000'],tolerance=0.),
       dict(enabled=True,exact=True,colors=['#000000'],tolerance=0.),
       dict(enabled=False,exact=True,colors=[],tolerance=0.)]


class NativeUICompletionTests(unittest.TestCase):
    def test_queued_stop_for_previous_runner_cannot_cancel_new_runner(self):
        from run_stop import StopEvent
        ui=self.ui();ui.overlay=None;ui.runner.stop=StopEvent()
        ui.handle_event('hotkey',dict(id=2,target_run_token='previous-run',source='message'))
        self.assertFalse(ui.runner.stop.is_set(),'A delayed F9 event cancelled a different run')

    def test_released_runner_identity_reuse_cannot_redirect_queued_stop(self):
        from engine import Runner
        ui=self.ui();ui.overlay=None;ui.q=queue.Queue();ui._hotkeys_stop=threading.Event()
        with tempfile.TemporaryDirectory() as tmp:
            ui.runner=Runner(lambda *args:None,tmp)
            previous_ref=weakref.ref(ui.runner);previous_stop=ui.runner.stop
            # Force the old object-ID scheme to alias after the previous task
            # is released; a task token must remain independent of addresses.
            with patch.object(app,'id',new=lambda runner:7,create=True), \
                 patch.object(app,'run_hotkeys',side_effect=lambda *args:args[4]('hotkey',dict(id=2,source='message'))):
                ui.hotkey_loop()
                self.assertTrue(previous_stop.is_set())
                ui.runner=Runner(lambda *args:None,tmp);gc.collect()
                self.assertIsNone(previous_ref())
                kind,data=ui.q.get_nowait();ui.handle_event(kind,data)
            self.assertFalse(ui.runner.stop.is_set(),'A queued stop was redirected by reused object identity')

    def test_current_hotkey_stop_keeps_hotkey_provenance(self):
        from run_stop import StopEvent
        ui=self.ui();ui.overlay=None;ui.runner.stop=StopEvent()
        ui.handle_event('hotkey',dict(id=2,target_run_token=ui.runner.run_token,source='poll'))
        self.assertTrue(ui.runner.stop.is_set())
        self.assertEqual(ui.runner.stop.diagnostic()['source'],'hotkey_poll')

    def ui(self):
        ui=app.App.__new__(app.App)
        ui.q=queue.Queue();ui.busy=True;ui.runner=types.SimpleNamespace(stop=threading.Event(),run_token='current-run')
        ui.active_rules=RULES;ui.cards=[types.SimpleNamespace(current=Mock(),best_label=Mock()) for _ in range(3)]
        ui.start=Mock();ui.status=Mock();ui.set_detail=Mock();ui.after=Mock();ui.report_callback_exception=Mock()
        ui.overlay=SearchOverlay.__new__(SearchOverlay)
        for name in ['activity','render','results','copy','collapse','resize_surface','clear_candidates']:
            setattr(ui.overlay,name,Mock())
        ui.overlay._dismissed=False;ui.overlay._candidate_data=None
        ui.overlay.candidate_rows={};ui.overlay.withdraw=Mock()
        ui.overlay._heartbeat_job=None
        ui.overlay._stage=None;ui.overlay._stage_started=0.;ui.overlay._deadline=None
        ui.q.put(('native_result',dict(RESULT)));ui.q.put(('finished',{}))
        return ui

    def assert_available(self,ui):
        self.assertFalse(ui.busy)
        self.assertIsNone(ui.runner)
        self.assertEqual(ui.start.configure.call_args.kwargs['state'],'normal')
        self.assertTrue(ui.q.empty())
        self.assertEqual(ui.after.call_args.args[0],60)

    def process(self,ui):
        try:ui.tick()
        except Exception as exc:self.fail('One presentation failure stopped the event poll: '+str(exc))

    def test_native_result_with_disabled_region_finishes_and_keeps_targets_editable(self):
        ui=self.ui()
        from result_history import describe_result
        row=describe_result(RESULT['actual_colors'],RULES)
        with patch('search_overlay.ct.CTkLabel'),patch.object(app,'save_result',return_value=row), \
             patch.object(app,'read_history',return_value=[row]):
            self.process(ui)
        self.assert_available(ui)
        self.assertEqual(ui.cards[2].best_label.configure.call_args.kwargs['text'],'#B360B5 · 未参与匹配')
        self.assertEqual(RULES[0]['colors'],['#000000'])

    def test_overlay_failure_still_processes_finished_and_schedules_next_poll(self):
        ui=self.ui();ui.overlay.handle=Mock(side_effect=RuntimeError('overlay widget destroyed'))
        with patch.object(app,'save_result',return_value={'regions':[],'maximum':None}), \
             patch.object(app,'read_history',return_value=[]):
            self.process(ui)
        self.assert_available(ui)
        self.assertEqual(ui.report_callback_exception.call_count,2)

    def test_result_history_failure_still_processes_finished_and_schedules_next_poll(self):
        ui=self.ui()
        with patch('search_overlay.ct.CTkLabel'),patch.object(app,'save_result',side_effect=ValueError('invalid result')):
            self.process(ui)
        self.assert_available(ui)
        self.assertEqual(ui.report_callback_exception.call_count,1)

    def test_destroyed_start_widget_does_not_retain_completed_runner(self):
        ui=self.ui();ui.q=queue.Queue();ui.q.put(('finished',{}))
        ui.start.configure.side_effect=RuntimeError('start widget destroyed')
        self.process(ui)
        self.assertFalse(ui.busy)
        self.assertIsNone(ui.runner)
        self.assertTrue(ui.q.empty())
        self.assertEqual(ui.after.call_args.args[0],60)


if __name__=='__main__':unittest.main()
