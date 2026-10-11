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
    def test_finish_hides_retry_surface_and_releases_main_window_controls(self):
        self.emit('native_retry_available',dict(enabled=True))
        self.emit('finished',{})
        self.assertFalse(self.ui.busy)
        self.assertEqual(self.ui.start.cget('state'),'normal')
        self.assertEqual(self.ui.overlay.state(),'withdrawn')
        self.ui.handle_event('hotkey',dict(id=3))
        self.assertEqual(self.requests,[])


if __name__=='__main__':unittest.main()
