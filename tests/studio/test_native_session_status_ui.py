"""Historical measurements remain explicit when the current board is unknown."""
import copy
import sys
import threading
from types import SimpleNamespace
import unittest

import test_native_ui_hit_testing as hit_testing
from search_overlay import SearchOverlay

RULES=[dict(enabled=True,exact=True,colors=['#000000'],tolerance=0.,priority=i+1) for i in range(3)]


@unittest.skipUnless(sys.platform=='win32','Session result UI requires Windows')
class NativeSessionStatusUITests(unittest.TestCase):
    def setUp(self):
        self.helper=hit_testing.NativeUIHitTestingTests();self.helper.setUp()
        self.addCleanup(self.helper.doCleanups)
        self.ui=self.helper.ui;self.ui.busy=True;self.ui.active_rules=copy.deepcopy(RULES)
        self.ui.runner=SimpleNamespace(stop=threading.Event())
        self.ui.overlay=SearchOverlay(self.ui,self.ui.stop,self.ui.select_candidate)
        self.ui.overlay.begin(copy.deepcopy(RULES),passive=True)
    def labels(self,widget):
        values=[]
        for child in widget.winfo_children():
            try:values.append(str(child.cget('text')))
            except Exception:pass
            values+=self.labels(child)
        return values
    def test_closed_board_shows_last_measurement_without_saving_a_current_match(self):
        result=dict(stop_reason='palette_ended',verified=False,accepted=False,screenshot_verified=False,
            actual_colors=[None]*3,actual_deltas=[None]*3,region_count=3,rules=RULES,outcome='stopped',
            last_verified_colors=['#EBEFE1','#838586','#D18658'],last_verified_deltas=[2.8,40.1,47.5],
            last_verified_screenshot=True,last_verified_captured_monotonic=123.)
        self.ui.overlay.handle('native_result',result);self.ui.handle_event('native_result',result)
        self.helper.pump(.03)
        for card,color in zip(self.ui.cards,result['last_verified_colors']):
            text=str(card.current.cget('text'))
            self.assertIn(color,text);self.assertIn('未确认',text)
        self.assertEqual(self.ui.history,[])
        text='\n'.join(self.labels(self.ui.overlay.results))
        self.assertIn('#EBEFE1',text);self.assertIn('未确认',text)
        self.ui.overlay.handle('finished',{});self.ui.handle_event('finished',{})
        self.helper.pump(.02)
        self.assertFalse(self.ui.busy)
        self.assertEqual(self.ui.overlay.state(),'withdrawn')
    def test_no_historical_screenshot_is_never_shown_as_verified_color(self):
        result=dict(stop_reason='session_binding_changed',verified=False,accepted=False,
            actual_colors=[None]*3,actual_deltas=[None]*3,region_count=3,rules=RULES,
            last_verified_colors=['#FFFFFF']*3,last_verified_deltas=[0.]*3,last_verified_screenshot=False)
        self.ui.handle_event('native_result',result);self.helper.pump(.02)
        self.assertTrue(all('#FFFFFF' not in str(c.current.cget('text')) for c in self.ui.cards))
        self.assertEqual(self.ui.history,[])


if __name__=='__main__':unittest.main()
