import importlib
import importlib.util
import unittest


class RunStopTests(unittest.TestCase):
    def event(self):
        self.assertIsNotNone(importlib.util.find_spec('run_stop'),'Stop provenance must be recorded')
        return importlib.import_module('run_stop').StopEvent()

    def test_first_source_survives_duplicate_ui_and_worker_stop_requests(self):
        event=self.event();event.request('hotkey_poll',virtual_key=0x78)
        event.request('ui_button');event.set()
        self.assertTrue(event.wait(0))
        self.assertEqual(event.diagnostic()['source'],'hotkey_poll')
        self.assertEqual(event.diagnostic()['virtual_key'],0x78)
        external=event.diagnostic();external['source']='changed'
        self.assertEqual(event.diagnostic()['source'],'hotkey_poll')

    def test_unattributed_set_does_not_claim_button_or_key_input(self):
        event=self.event();event.set()
        self.assertEqual(event.diagnostic()['source'],'unattributed_stop_flag')

    def test_clear_does_not_carry_previous_stop_source_into_new_run(self):
        event=self.event();event.request('ui_button');event.clear()
        self.assertFalse(event.is_set());self.assertIsNone(event.diagnostic())
        event.request('window_close');self.assertEqual(event.diagnostic()['source'],'window_close')
