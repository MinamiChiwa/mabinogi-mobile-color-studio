"""Startup gets30s recognition grace; the closing reserve is independent."""
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import numpy as np
from native_live.same_session_dye_planner import _frames


class NativeTimerPolicyTests(unittest.TestCase):
    def checkpoint(self):return {'client_hex':['#112233']*3}
    def test_unknown_early_timer_is_valid_observation(self):
        frames=[dict(hex=['#112233']*3,remaining_seconds=119,captured_monotonic=10.),
                dict(hex=['#112233']*3,remaining_seconds=None,captured_monotonic=11.)]
        self.assertIsNone(_frames(self.checkpoint(),frames)[0])
    def test_timer_jump_after_early_window_is_advisory_and_color_read_survives(self):
        frames=[dict(hex=['#112233']*3,remaining_seconds=90,captured_monotonic=40.),
                dict(hex=['#112233']*3,remaining_seconds=17,captured_monotonic=41.)]
        result=_frames(self.checkpoint(),frames)
        self.assertIsNone(result[0]);self.assertIsNone(frames[1]['remaining_seconds'])
        self.assertEqual(frames[1]['timer_confidence'],'discontinuity_advisory')
    def test_startup_skips_timer_ocr_but_still_reads_hex(self):
        from native_live import project_probe_io as io
        scene=SimpleNamespace(cards=[],markers=[],board=[0,0,500,500])
        with patch.object(io,'recognize',return_value=scene), \
             patch.object(io,'read_codes',return_value=['#112233']*3), \
             patch.object(io,'read_timer',side_effect=AssertionError('Timer OCR during grace')):
            result=io.read_probe_frame(np.zeros((960,1280,3),dtype=np.uint8),deadline=100.,clock=lambda:1.,timer_mode='skip')
        self.assertEqual(result['hex'],['#112233']*3);self.assertIsNone(result['remaining_seconds'])
    def test_later_timer_timeout_does_not_discard_good_hex(self):
        from native_live import project_probe_io as io
        scene=SimpleNamespace(cards=[],markers=[],board=[0,0,500,500])
        with patch.object(io,'recognize',return_value=scene), \
             patch.object(io,'read_codes',return_value=['#112233']*3), \
             patch.object(io,'read_timer',side_effect=TimeoutError('Timer OCR budget')):
            result=io.read_probe_frame(np.zeros((960,1280,3),dtype=np.uint8),deadline=100.,clock=lambda:1.,timer_mode='advisory')
        self.assertEqual(result['hex'],['#112233']*3);self.assertIsNone(result['remaining_seconds'])
    def test_bad_timestamp_is_rejected_even_when_timer_is_advisory(self):
        frames=[dict(hex=['#112233']*3,remaining_seconds=13,captured_monotonic=10.,timer_advisory=True),
                dict(hex=['#112233']*3,remaining_seconds=None,captured_monotonic=9.,timer_advisory=True)]
        with self.assertRaises(ValueError):_frames(self.checkpoint(),frames)


if __name__=='__main__':unittest.main()
