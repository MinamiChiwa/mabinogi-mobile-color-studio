import json
import unittest
import numpy as np
from analyze_live_atlas import frame_sequence
from micro_return_probe import ReturnLimits, run_micro_return


ANCHORS = {'x': [[250, 250], [274, 250]], 'y': [[250, 250], [250, 274]]}


class SimulatedReturnAdapter:
    """Reciprocal zoom about individual anchors, with explicit fault hooks."""
    def __init__(self):
        self.now = 0.
        self.pose = np.eye(3)
        self.ctx = 'same-session-geometry'
        self.stopped = False
        self.released = False
        self.wheels = []
        self.captures = []
        self.reads = 0
        self.after_wheel = lambda: None
        self.before_input = lambda: None
        self.after_capture = lambda: None
        self.after_read = lambda: None
        self.after_motion = lambda: None
        self.after_pause = lambda: None
        self.codes = lambda frame: ['#123456', '#789ABC', '#DEF012'] if frame['notches'] % 4 == 0 else ['#234567', '#89ABCD', '#EF0123']

    def check(self):
        if self.stopped:
            raise RuntimeError('Stopped / focus / countdown guard')

    def context(self):
        return self.ctx

    def marker_points(self):
        return [[80, 350], [250, 250], [420, 360]]

    def capture(self, name):
        self.now += .05
        frame = dict(name=name, pose=self.pose.copy(), notches=len(self.wheels))
        self.captures.append(frame)
        self.after_capture()
        return frame

    def motion(self, reference, frame):
        self.now += .05
        matrix = (frame['pose'] @ np.linalg.inv(reference['pose']))[:2]
        self.after_motion()
        return dict(matrix=matrix.tolist(), scale=float(np.hypot(*matrix[:, 0])),
                    angle=float(np.degrees(np.arctan2(matrix[1, 0], matrix[0, 0]))), inliers=100)

    def read_codes(self, frame):
        self.now += .44
        self.reads += 1
        self.after_read()
        return self.codes(frame)

    def wheel(self, notch, anchor, *, deadline, guard):
        # Model a cursor move that may consume time or change foreground before
        # the final wheel boundary. Recheck there, not only in the controller.
        self.before_input()
        guard()
        if self.now >= deadline:
            raise RuntimeError('Input deadline')
        scale = 1.01 if notch == 1 else 1 / 1.01
        zoom = np.eye(3)
        zoom[:2, :2] *= scale
        zoom[:2, 2] = (1 - scale) * np.asarray(anchor)
        self.pose = zoom @ self.pose
        self.wheels.append(dict(notch=notch, anchor=np.asarray(anchor).tolist(), at=self.now))
        self.now += .01
        self.after_wheel()

    def pause(self, seconds):
        self.now += seconds
        self.after_pause()

    def release(self):
        self.released = True


class MicroReturnTests(unittest.TestCase):
    def run_probe(self, adapter=None, deadline=60., **kwargs):
        adapter = adapter or SimulatedReturnAdapter()
        return run_micro_return(adapter, ANCHORS, deadline, clock=lambda: adapter.now, **kwargs)

    def test_ideal_roundtrips_swap_anchors_and_verify_all_three_colors(self):
        a = SimulatedReturnAdapter()
        r = self.run_probe(a)
        self.assertTrue(r['protocol_passed'], r['error'])
        self.assertTrue(r['returned_to_baseline'])
        self.assertEqual(r['axes_completed'], ['x', 'y'])
        self.assertEqual(len(a.wheels), 8)
        self.assertEqual([v['notch'] for v in a.wheels], [1, -1] * 4)
        self.assertEqual([v['anchor'] for v in a.wheels[:4]],
                         [ANCHORS['x'][0], ANCHORS['x'][1], ANCHORS['x'][1], ANCHORS['x'][0]])
        np.testing.assert_allclose(a.pose, np.eye(3), atol=1e-12)
        self.assertEqual(len(a.captures), 10)
        self.assertEqual(a.reads, 10)
        motions = [v for v in r['records'] if v['kind'] == 'micro_return_motion']
        self.assertEqual(len(motions), 10)
        self.assertTrue(all(v['reference'] == 'baseline_0' for v in motions))
        self.assertTrue(all(len(v['point_displacements']) == 3 for v in motions))
        self.assertFalse(r['live_validated'])
        self.assertTrue(a.released)
        json.dumps(r, allow_nan=False)

    def test_stop_at_each_individual_input_boundary_never_compensates(self):
        for blocked in range(1, 9):
            with self.subTest(blocked=blocked):
                a = SimulatedReturnAdapter()
                def stop():
                    if len(a.wheels) + 1 == blocked:
                        a.stopped = True
                a.before_input = stop
                r = self.run_probe(a)
                self.assertEqual(len(a.wheels), blocked - 1)
                self.assertEqual(r['reason'], 'stopped')
                self.assertFalse(r['current_verified'])
                self.assertFalse(r['returned_to_baseline'])
                self.assertIsNotNone(r['baseline'])
                self.assertTrue(a.released)

    def test_stop_immediately_after_each_notch_never_sends_next_notch(self):
        for count in range(1, 9):
            with self.subTest(count=count):
                a = SimulatedReturnAdapter()
                def stop():
                    if len(a.wheels) == count:
                        a.stopped = True
                a.after_wheel = stop
                r = self.run_probe(a)
                self.assertEqual(len(a.wheels), count)
                self.assertFalse(r['current_verified'])
                self.assertFalse(r['protocol_passed'])
                self.assertTrue(a.released)

    def test_stop_during_wait_between_pair_halves(self):
        a = SimulatedReturnAdapter()
        def stop():
            if len(a.wheels) == 1:
                a.stopped = True
        a.after_pause = stop
        r = self.run_probe(a)
        self.assertEqual(len(a.wheels), 1)
        self.assertFalse(r['returned_to_baseline'])

    def test_deadline_while_positioning_cursor_blocks_final_input(self):
        a = SimulatedReturnAdapter()
        a.before_input = lambda: setattr(a, 'now', 26.)
        r = self.run_probe(a)
        self.assertEqual(a.wheels, [])
        self.assertEqual(r['attempted_notches'], 1)
        self.assertEqual(r['completed_notches'], 0)
        self.assertIn('deadline', r['error'])

    def test_context_change_between_halves_stops_without_return(self):
        a = SimulatedReturnAdapter()
        a.after_wheel = lambda: setattr(a, 'ctx', 'changed-geometry')
        r = self.run_probe(a)
        self.assertEqual(len(a.wheels), 1)
        self.assertIn('geometry', r['error'])

    def test_reserve_rechecked_between_forward_and_reverse_pair_halves(self):
        for count, delay in ((1, 13.), (3, 19.)):
            with self.subTest(count=count):
                a = SimulatedReturnAdapter()
                def slow():
                    if len(a.wheels) == count:
                        a.now += delay
                a.after_wheel = slow
                r = self.run_probe(a)
                self.assertEqual(len(a.wheels), count)
                self.assertIn('reserve', r['error'])
                self.assertLess(a.now, r['deadline'])
                self.assertFalse(r['returned_to_baseline'])
                self.assertTrue(a.released)

    def test_missing_or_unstable_baseline_hex_sends_no_input(self):
        for codes in ([None, '#123456', '#ABCDEF'], ['123456'] * 3,
                      ['#12345O'] * 3, ['#123456'] * 2, None, 'unstable'):
            with self.subTest(codes=codes):
                a = SimulatedReturnAdapter()
                a.codes = lambda frame: (['#123456'] * 3 if a.reads % 2 else ['#654321'] * 3) if codes == 'unstable' else codes
                r = self.run_probe(a)
                self.assertEqual(a.wheels, [])
                self.assertFalse(r['current_verified'])
                self.assertTrue(a.released)

    def test_deadline_after_capture_registration_or_ocr_invalidates_state(self):
        for hook in ('after_capture', 'after_motion', 'after_read'):
            with self.subTest(hook=hook):
                a = SimulatedReturnAdapter()
                setattr(a, hook, lambda: setattr(a, 'now', 30.))
                r = self.run_probe(a)
                self.assertEqual(a.wheels, [])
                self.assertIn('deadline', r['error'])
                self.assertFalse(r['current_verified'])

    def test_changed_or_missing_ocr_after_forward_pair_prevents_return(self):
        for unstable in (False, True):
            a = SimulatedReturnAdapter()
            def codes(frame):
                if frame['notches'] == 0:
                    return ['#123456'] * 3
                return ['#234567'] * 3 if unstable and a.reads % 2 else [None] * 3
            a.codes = codes
            r = self.run_probe(a)
            self.assertEqual(len(a.wheels), 2)
            self.assertFalse(r['current_verified'])

    def test_stable_hex_mismatch_after_return_is_failure(self):
        a = SimulatedReturnAdapter()
        a.codes = lambda frame: ['#123456', '#789ABC', '#DEF012'] if frame['notches'] == 0 else ['#123456', '#789ABD', '#DEF012']
        r = self.run_probe(a)
        self.assertEqual(len(a.wheels), 4)
        self.assertIn('all three HEX', r['error'])
        self.assertEqual(r['axes_completed'], [])
        self.assertFalse(r['current_verified'])

    def test_return_geometry_mismatch_with_identical_hex_is_failure(self):
        a = SimulatedReturnAdapter()
        a.codes = lambda frame: ['#123456'] * 3
        def drift():
            if len(a.wheels) == 4:
                a.pose[0, 2] += .05
        a.after_wheel = drift
        r = self.run_probe(a)
        self.assertEqual(len(a.wheels), 4)
        self.assertFalse(r['returned_to_baseline'])
        self.assertIn('baseline geometry', r['error'])

    def test_small_scale_change_that_splits_marker_motion_stops(self):
        a = SimulatedReturnAdapter()
        def drift():
            if len(a.wheels) == 2:
                a.pose[:2, :2] *= 1.001
        a.after_wheel = drift
        r = self.run_probe(a)
        self.assertEqual(len(a.wheels), 2)
        self.assertIn('three-marker', r['error'])
        self.assertFalse(r['returned_to_baseline'])

    def test_baseline_must_stay_still_between_reads(self):
        a = SimulatedReturnAdapter()
        a.after_pause = lambda: a.pose.__setitem__((0, 2), .1)
        r = self.run_probe(a)
        self.assertEqual(a.wheels, [])
        self.assertIn('Board moved', r['error'])

    def test_failed_forward_or_reverse_registration_has_no_blind_retry(self):
        for count in (2, 4):
            a = SimulatedReturnAdapter()
            original = a.motion
            a.motion = lambda ref, frame: None if frame['notches'] >= count else original(ref, frame)
            r = self.run_probe(a)
            self.assertEqual(len(a.wheels), count)
            self.assertFalse(r['returned_to_baseline'])
            self.assertFalse(r['current_verified'])
            failed = [v for v in r['records'] if v['kind'] == 'micro_return_motion' and v['motion'] is None]
            self.assertEqual(len(failed), 1)

    def test_no_actual_motion_or_excessive_motion_stops_after_first_pair(self):
        for translation in (0., 2.):
            a = SimulatedReturnAdapter()
            def replace():
                if len(a.wheels) == 2:
                    a.pose = np.eye(3)
                    a.pose[0, 2] = translation
            a.after_wheel = replace
            r = self.run_probe(a)
            self.assertEqual(len(a.wheels), 2)
            self.assertIn('bounded motion', r['error'])

    def test_reserve_prevents_departure_and_preserves_verified_baseline(self):
        a = SimulatedReturnAdapter()
        r = self.run_probe(a, deadline=8.)
        self.assertEqual(a.wheels, [])
        self.assertTrue(r['baseline_verified_now'])
        self.assertFalse(r['returned_to_baseline'])
        self.assertEqual(r['reason'], 'insufficient_roundtrip_budget')

    def test_y_is_skipped_when_x_passes_but_budget_is_short(self):
        a = SimulatedReturnAdapter()
        r = self.run_probe(a, deadline=14.)
        self.assertEqual(len(a.wheels), 4)
        self.assertEqual(r['axes_completed'], ['x'])
        self.assertTrue(r['returned_to_baseline'])
        self.assertFalse(r['protocol_passed'])
        self.assertEqual(r['reason'], 'insufficient_roundtrip_budget')

    def test_unexpected_forward_delay_prevents_underbudget_return(self):
        a = SimulatedReturnAdapter()
        def delay():
            if len(a.wheels) == 2:
                a.now += 16.
        a.after_wheel = delay
        r = self.run_probe(a)
        self.assertEqual(len(a.wheels), 2)
        self.assertIn('budget', r['error'])
        self.assertFalse(r['current_verified'])

    def test_shared_and_stage_deadlines_cannot_be_extended(self):
        for deadline, effective in ((9., 9.), (60., 25.)):
            r = self.run_probe(deadline=deadline)
            self.assertEqual(r['deadline'], effective)
        a = SimulatedReturnAdapter()
        a.now = 55.
        r = self.run_probe(a, deadline=60.)
        self.assertEqual(r['deadline'], 60.)
        self.assertEqual(a.wheels, [])
        with self.assertRaises(ValueError):
            ReturnLimits(stage_seconds=26)

    def test_expired_or_too_short_budget_only_releases(self):
        for deadline in (0., 3.):
            a = SimulatedReturnAdapter()
            r = self.run_probe(a, deadline=deadline)
            self.assertEqual(a.wheels, [])
            self.assertEqual(a.captures, [])
            self.assertFalse(r['current_verified'])
            self.assertTrue(a.released)

    def test_invalid_marker_or_anchor_geometry_prevents_input(self):
        a = SimulatedReturnAdapter()
        a.marker_points = lambda: [[1, 1]]
        r = self.run_probe(a)
        self.assertIn('marker points', r['error'])
        self.assertEqual(a.wheels, [])
        a = SimulatedReturnAdapter()
        r = run_micro_return(a, {'x': [[0, 0], [0, 24]], 'y': ANCHORS['y']}, 60., clock=lambda: a.now)
        self.assertIn('Anchor separation', r['error'])
        self.assertEqual(a.wheels, [])

    def test_release_failure_or_delay_cannot_publish_success(self):
        for mode in ('slow', 'failure', 'stopped'):
            a = SimulatedReturnAdapter()
            def release():
                if mode == 'slow':
                    a.now = 30.
                elif mode == 'stopped':
                    a.stopped = True
                else:
                    raise RuntimeError('release failed')
            a.release = release
            r = self.run_probe(a)
            self.assertFalse(r['protocol_passed'])
            self.assertFalse(r['current_verified'])
            self.assertIsNotNone(r['error'])

    def test_diagnostic_log_cannot_be_loaded_as_atlas(self):
        r = self.run_probe()
        with self.assertRaisesRegex(ValueError, 'not atlas'):
            frame_sequence(r['records'])
        with self.assertRaisesRegex(ValueError, 'not atlas'):
            frame_sequence([dict(kind='CAPTURE_COMPLETE', strategy='micro_return')])


if __name__ == '__main__':
    unittest.main()
