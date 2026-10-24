"""Recorded stop-after-result regression: no input, accurate cause and retained readings."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from platform_win import Interrupted
from run_stop import StopEvent
from screenshot_search import actual_result
from screenshot_live import _finish_interruption,_publish
from screenshot_presentation import result_text

class ScreenshotStopResultTests(unittest.TestCase):
    def controller(self):
        rules=[dict(enabled=True,colors=['#000000'],exact=True,tolerance=0,priority=i+1) for i in range(2)]
        value=actual_result(['#111111','#222222'],rules)
        stop=StopEvent();stop.request('ui_button')
        return SimpleNamespace(current=value,best=value,rules=rules,actions=[],observations=[],
            owner=SimpleNamespace(stop=stop,event=Mock()),budget=SimpleNamespace(remaining=lambda:15),
            write=Mock(),observe=Mock(),safe_restore=Mock(return_value=dict(verified=False)),
            input_in_progress=False,input_uncertain=False)

    def test_stop_after_verified_result_keeps_measurement_and_sends_no_input(self):
        c=self.controller();result=_finish_interruption(c,Interrupted('stop',reason='user_stop'))
        self.assertTrue(result['verified']);self.assertEqual(result['actual_colors'],['#111111','#222222'])
        self.assertEqual(result['interruption_reason'],'user_stop')
        c.observe.assert_not_called();c.safe_restore.assert_not_called()

    def test_unconfirmed_match_is_not_reconfirmed_after_stop(self):
        c=self.controller();c.current=actual_result(['#000000']*2,c.rules)
        result=_finish_interruption(c,Interrupted('stop',reason='user_stop'))
        self.assertTrue(result['verified']);self.assertFalse(result['accepted'])
        c.observe.assert_not_called()

    def test_focus_loss_invalidates_current_but_keeps_last_measured_colors(self):
        c=self.controller();result=_finish_interruption(c,Interrupted('focus',reason='focus_lost'))
        self.assertFalse(result['verified']);self.assertEqual(result['interruption_reason'],'focus_lost')
        self.assertEqual(result['last_verified_colors'],['#111111','#222222'])
        self.assertEqual(result['last_verified_screenshot'],True)
        self.assertIn('焦点',result_text(result)[0])

    def test_partial_gesture_never_claims_old_colors_as_current(self):
        c=self.controller();c.current=None;c.input_in_progress=True
        result=_finish_interruption(c,Interrupted('stop',reason='user_stop'))
        self.assertFalse(result['verified']);c.observe.assert_not_called()

    def test_unknown_interruption_is_not_called_user_stop(self):
        c=self.controller();c.owner.stop.clear()
        result=_finish_interruption(c,Interrupted('unknown'))
        self.assertEqual(result['interruption_reason'],'unknown_interruption')
        self.assertFalse(result['verified'])

    def test_unverified_partial_read_does_not_hide_older_verified_read(self):
        c=self.controller();c.observations=[c.current];c.current=dict(verified=False)
        result=_finish_interruption(c,Interrupted('focus',reason='focus_lost'))
        self.assertEqual(result['last_verified_colors'],['#111111','#222222'])
        self.assertEqual(c.owner.event.call_count,1)

    def test_hotkey_diagnostic_preserved_without_claiming_player_intent(self):
        c=self.controller();c.owner.stop.clear();c.owner.stop.request('hotkey_message')
        result=_finish_interruption(c,Interrupted('stop',reason='user_stop'))
        self.assertEqual(result['interruption_reason'],'stop_hotkey')
        self.assertEqual(result['stop_diagnostic']['source'],'hotkey_message')
        self.assertTrue(result['verified']);c.safe_restore.assert_not_called()

    def test_interruption_during_final_confirmation_keeps_typed_cause(self):
        c=self.controller();c.current=actual_result(['#000000']*2,c.rules)
        c.observations=[dict(c.current)]
        c.observe.side_effect=Interrupted('focus',reason='focus_lost')
        result=_publish(c)
        self.assertEqual(result['interruption_reason'],'focus_lost')
        self.assertEqual(result['stop_reason'],'interrupted')
        self.assertFalse(result['verified']);self.assertEqual(c.owner.event.call_count,1)
