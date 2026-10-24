"""Real Tk preview result and repeated retry; isolated player data, no game IO."""
import copy,threading,unittest
from types import SimpleNamespace
from unittest.mock import patch
import app
from search_overlay import SearchOverlay
import test_native_ui_hit_testing as hit

RULES=[dict(enabled=True,exact=True,colors=['#FFFFFF'],tolerance=8,priority=i+1) for i in range(3)]

class ScreenshotUITests(unittest.TestCase):
    def setUp(self):
        self.helper=hit.NativeUIHitTestingTests();self.helper.setUp();self.addCleanup(self.helper.doCleanups)
        self.ui=self.helper.ui;self.ui.search_strategy.set('screenshot');self.ui.active_rules=copy.deepcopy(RULES)
        self.ui.busy=True;self.requests=[]
        self.ui.runner=SimpleNamespace(stop=threading.Event(),request_retry=lambda:self.requests.append(True))
        self.ui.overlay=SearchOverlay(self.ui,self.ui.stop,self.ui.select_candidate)
        self.ui.overlay.begin(copy.deepcopy(RULES),passive=True)
        self.helper.pump(.02)
    def emit(self,kind,data):
        self.ui.overlay.handle(kind,data);self.ui.handle_event(kind,data);self.helper.pump(.02)
    def test_next_run_clears_previous_actual_and_color_strips_before_reading(self):
        from result_history import describe_result
        old=['#FA8B28','#A9685B','#69B55B']
        self.ui.display_best(describe_result(old,self.ui.active_rules))
        for card,color in zip(self.ui.cards,old):card.current.configure(text='当前颜色  '+color)
        self.ui.finish_run()
        with patch.object(app,'build_runner',return_value=SimpleNamespace(launch=lambda *a,**kw:None)), \
                patch.object(app.threading,'Thread'):
            self.ui.go()
        for card,color in zip(self.ui.cards,old):
            self.assertNotIn(color,str(card.current.cget('text')))
            self.assertNotIn(color,str(card.best_label.cget('text')))
            self.assertEqual(card.best_label.cget('fg_color'),'#28364A')
        self.assertIsNone(self.ui.best_summary)
        self.assertEqual(self.helper.errors,[])
    def test_real_card_labels_follow_repeated_native_readbacks_while_busy(self):
        self.ui.search_strategy.set('native')
        for colors in (['#112233','#445566','#778899'],['#AABBCC','#DDEEFF','#334455'],['#000000','#FFFFFF','#FF0000']):
            self.emit('native_colors',dict(colors=colors,screenshot_verified=False))
            for card,color in zip(self.ui.cards,colors):
                self.assertIn(color,str(card.current.cget('text')))
                self.assertIn(color,str(card.best_label.cget('text')))
                self.assertEqual(card.best_label.cget('fg_color'),color)
        self.assertTrue(self.ui.busy)
        self.assertEqual(self.helper.errors,[])
    def test_preview_retry_can_be_used_twice_and_finished_releases_controls(self):
        for _ in range(2):
            self.emit('native_retry_reset',dict(status='searching',backend='screenshot'))
            self.emit('native_retry_available',dict(enabled=True,backend='screenshot'))
            self.assertEqual(self.ui.overlay.retry_button.cget('state'),'normal')
            self.ui.overlay.retry_button.invoke()
            self.emit('native_retry_reset',dict(status='zooming',backend='screenshot'))
        self.assertEqual(len(self.requests),2)
        self.emit('finished',{})
        self.assertFalse(self.ui.busy);self.assertEqual(self.ui.overlay.state(),'withdrawn')
        self.helper.hit(self.ui.cards[0].target_entry)
        self.assertEqual(self.helper.errors,[])
    def test_preview_actual_result_and_unrestored_history_are_distinct(self):
        value=dict(backend='screenshot',actual_colors=['#FFFFFF','#AEAEAE','#EDEEEE'],
            actual_deltas=[0.,30.,5.],verified=True,accepted=False,best_current=False,
            outcome='compromise',best_actual_colors=['#FFFFFF']*3)
        self.emit('screenshot_result',value)
        self.assertIn('未完全恢复',str(self.ui.detail.cget('text')))
        self.assertIn('#AEAEAE',str(self.ui.cards[1].current.cget('text')))
        self.assertEqual(self.ui.history[0]['regions'][1]['color'],'#AEAEAE')
        self.assertEqual(self.ui.overlay.candidate_rows,{})
        self.assertEqual(self.helper.errors,[])

    def test_stopped_unverified_result_keeps_historical_readings_in_both_windows(self):
        colors=['#112233','#445566','#778899']
        self.emit('screenshot_result',dict(backend='screenshot',verified=False,accepted=False,
            stop_reason='interrupted',interruption_reason='focus_lost',
            last_verified_screenshot=True,last_verified_colors=colors,last_verified_deltas=[1.,2.,3.]))
        for card,color in zip(self.ui.cards,colors):
            self.assertIn(color,str(card.current.cget('text')))
            self.assertIn('上次实测',str(card.current.cget('text')))
        labels=[str(widget.cget('text')) for widget in self.ui.overlay.results.winfo_children()]
        for color in colors:self.assertTrue(any(color in label and '上次实测' in label for label in labels),labels)
        self.assertEqual(self.helper.errors,[])

if __name__=='__main__':unittest.main()
