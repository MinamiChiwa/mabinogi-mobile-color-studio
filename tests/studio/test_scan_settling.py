import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from platform_win import Interrupted
from scan_settling import ScanSettlingObserver
from live_atlas_capture import CaptureGame


class FakeClock:
    def __init__(self): self.now = 0.
    def __call__(self): return self.now
    def sleep(self, seconds): self.now += seconds


class FakeGame:
    initial = (0, 0, 360, 360)

    def __init__(self, clock, frames, latency=.04):
        self.clock = clock
        self.frames = iter(frames)
        self.latency = latency
        self.calls = []

    def check(self): pass
    def pause(self, seconds): self.clock.sleep(seconds)
    def drag(self, board, dx, dy):
        self.calls.append(('drag', dx, dy))
        self.clock.sleep(.692)
    def move_to(self, point): self.calls.append(('park', point))
    def capture(self):
        self.calls.append(('capture', self.clock()))
        value = next(self.frames)
        self.clock.sleep(self.latency)
        if isinstance(value, Exception): raise value
        return value


class SettlingTests(unittest.TestCase):
    def setUp(self):
        self.scene = SimpleNamespace(board=(20,20,320,320),
                                     markers=[(70,100),(170,170),(270,260)], cards=[])
        self.observer = ScanSettlingObserver(self.scene,observe=True)
        self.clock = FakeClock()
        self.previous = np.random.default_rng(929).integers(0,256,(360,360,3),dtype=np.uint8)
        self.frame = np.roll(self.previous, 10, axis=1)
        self.action = dict(dx=60,dy=0)

    def run_step(self, game):
        return self.observer.capture_step(game,self.scene,self.action,self.previous,self.clock)

    def test_normal_scan_only_captures_baseline_with_original_wait_and_drag(self):
        self.observer=ScanSettlingObserver(self.scene)
        game=FakeGame(self.clock,[self.frame])
        with patch.object(self.observer,'compare',side_effect=AssertionError('Unexpected diagnostics')):
            sample=self.run_step(game)
        self.assertIs(sample.image,self.frame)
        self.assertEqual(game.calls[:2],[('drag',60,0),('park',(180,54))])
        self.assertEqual(sum(call[0]=='capture' for call in game.calls),1)
        self.assertAlmostEqual(sample.capture_started,.692+.38)
        self.assertEqual(sample.probes,())
        self.assertEqual(sample.timing['probe_times'],[])
        self.assertEqual(sample.timing['comparisons'],{})
        self.assertEqual(self.observer.summary()['mode'],'baseline')
        self.assertEqual(self.observer.summary()['compared_frames'],0)

    def test_normal_scan_propagates_f9_without_a_recovery_capture(self):
        self.observer=ScanSettlingObserver(self.scene)
        game=FakeGame(self.clock,[Interrupted('F9'),self.frame])
        with self.assertRaisesRegex(Interrupted,'F9'):self.run_step(game)
        self.assertEqual(sum(call[0]=='capture' for call in game.calls),1)
        self.assertEqual(sum(call[0]=='drag' for call in game.calls),1)
        self.assertEqual(self.observer.rows,[])

    def test_identical_early_frames_never_replace_baseline_and_keep_drag(self):
        final = self.frame.copy()
        game = FakeGame(self.clock,[self.frame,self.frame,final])
        sample = self.run_step(game)
        self.assertIs(sample.image,final)
        self.assertEqual(game.calls[:2],[('drag',60,0),('park',(180,54))])
        self.assertEqual(sum(c[0]=='drag' for c in game.calls),1)
        self.assertAlmostEqual(sample.capture_started,.692+.38)
        self.assertTrue(sample.timing['early_matches_baseline'])
        self.assertTrue(sample.timing['motion_observed'])
        self.assertAlmostEqual(sample.timing['potential_saving_seconds'],.20)
        self.assertEqual(self.observer.summary()['identical_early_frames'],1)
        self.assertEqual(sample.timing['selected'],'baseline')

    def test_late_update_invalidates_two_identical_early_stale_frames(self):
        game = FakeGame(self.clock,[self.previous,self.previous,self.frame])
        sample = self.run_step(game)
        self.assertIs(sample.image,self.frame)
        self.assertTrue(sample.timing['comparisons']['early_to_check']['equal'])
        self.assertFalse(sample.timing['comparisons']['check_to_reference']['equal'])
        self.assertFalse(sample.timing['early_matches_baseline'])
        self.assertEqual(sample.timing['potential_saving_seconds'],0)

    def test_no_texture_response_is_not_evidence_for_fast_sampling(self):
        game = FakeGame(self.clock,[self.previous]*3)
        sample = self.run_step(game)
        self.assertTrue(sample.timing['early_matches_baseline'])
        self.assertFalse(sample.timing['motion_observed'])
        self.assertEqual(sample.timing['potential_saving_seconds'],0)

    def test_all_material_pixels_checked_and_ui_excluded(self):
        a = self.observer.crop(self.frame).copy()
        for region, mask in enumerate(self.observer.masks):
            b=a.copy();y,x=np.argwhere(mask)[-1];b[y,x,0]^=1
            result=self.observer.compare(a,b)
            self.assertFalse(result['equal'])
            self.assertEqual(result['regions'][region]['changed_pixels'],1)
        b=a.copy();b[~self.observer.masks.any(axis=0)]^=255
        self.assertTrue(self.observer.compare(a,b)['equal'])
        self.assertFalse(self.observer.compare(a,a[:-1])['equal'])

    def test_slow_capture_disables_probes_without_adding_a_second_probe(self):
        game = FakeGame(self.clock,[self.frame]*3,latency=.24)
        first=self.run_step(game)
        self.assertEqual(len(first.probes),1)
        self.assertEqual(first.timing['fallback_reason'],'probe_capture_too_slow')
        self.assertAlmostEqual(first.capture_started,.692+.38)
        second=self.run_step(game)
        self.assertEqual(len(second.probes),0)
        self.assertEqual(sum(c[0]=='capture' for c in game.calls),3)
        self.assertEqual(second.timing['selected'],'baseline')

    def test_optional_capture_error_returns_normal_frame_and_disables_probes(self):
        game=FakeGame(self.clock,[OSError('capture busy'),self.frame])
        sample=self.run_step(game)
        self.assertIs(sample.image,self.frame)
        self.assertTrue(sample.timing['fallback_reason'].startswith('probe_unavailable'))
        self.assertEqual(sample.timing['comparisons'],{})
        self.assertAlmostEqual(sample.capture_started,.692+.38)

    def test_probe_overrun_is_recorded_and_disables_later_probes(self):
        game=FakeGame(self.clock,[self.frame]*3,latency=.40)
        first=self.run_step(game)
        self.assertGreater(first.timing['baseline_late_seconds'],.09)
        self.assertIsNotNone(first.timing['fallback_reason'])
        second=self.run_step(game)
        self.assertEqual(second.probes,())
        self.assertAlmostEqual(second.timing['baseline_late_seconds'],0.)

    def test_invalid_probe_geometry_keeps_baseline_and_disables_observation(self):
        game=FakeGame(self.clock,[self.frame[:10],self.frame[:10],self.frame])
        sample=self.run_step(game)
        self.assertIs(sample.image,self.frame)
        self.assertFalse(sample.timing['early_matches_baseline'])
        self.assertEqual(sample.timing['fallback_reason'],'invalid_comparison_geometry')

    def test_cancel_or_focus_loss_is_not_swallowed_or_retried(self):
        for message in ('F9','focus lost','deadline'):
            with self.subTest(message=message):
                self.setUp()
                game=FakeGame(self.clock,[Interrupted(message),self.frame])
                with self.assertRaisesRegex(Interrupted,message):self.run_step(game)
                self.assertEqual(sum(c[0]=='capture' for c in game.calls),1)
                self.assertEqual(sum(c[0]=='drag' for c in game.calls),1)

    def test_scan_wait_sleeps_only_remaining_time_and_checks_after_last_sleep(self):
        game=CaptureGame.__new__(CaptureGame)
        checks=[]
        game.check=lambda:checks.append(self.clock())
        with patch('live_atlas_capture.time.monotonic',self.clock), \
             patch('live_atlas_capture.time.sleep',self.clock.sleep):
            game.pause_until(.035)
        self.assertAlmostEqual(self.clock(),.035)
        self.assertEqual(len(checks),3)
        self.assertAlmostEqual(checks[-1],.035)


if __name__=='__main__':unittest.main()
