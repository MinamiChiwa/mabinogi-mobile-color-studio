"""Protected phase budgets must preserve the real IO boundary's input guards."""
import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from input_gestures import PointerGesture
from native_live.project_closed_loop_io import ProjectClosedLoopIO


class ControlledClock:
    def __init__(self):
        self.now = 10.

    def monotonic(self):
        return self.now


class ControlledGame:
    def __init__(self, clock):
        self.clock = clock
        self.inputs = []
        self.completed = True
        self.last_input_trace = []

    def check(self):
        pass

    def perform_gesture(self, gesture):
        self.inputs.append(gesture.record())
        self.clock.now += gesture.duration
        self.last_input_trace = [dict(actual_client=list(p)) for p in gesture.points]
        return self.completed


class ControlledBackend:
    def __init__(self, observation):
        self.observation = observation

    def process_identity(self):
        return self.observation['process_identity']

    def probe(self, address, deadline, check):
        check()
        return copy.deepcopy(self.observation)

    def observe_motion(self, address, deadline, check, **kwargs):
        check()
        return copy.deepcopy(self.observation)


class NativeProtectedIOTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.clock = ControlledClock()
        self.game = ControlledGame(self.clock)
        observation = dict(
            active=True, process_identity=[42, 11, 1000, 'build'], session_token=['palette'],
            motion=dict(binding={'address': 100}, settings={'minimum_scale': .5},
                        pose=dict(position=[0., 0.], scale=1., rotation_degrees=0.),
                        animators_done=True),
            geometry_diagnostic={'geometry': 'bound'}, window_context={'window': {'hwnd': 7}},
            window_mapping_candidate={'client_board_candidate': [0., 0., 500., 500.]})
        self.backend = ControlledBackend(copy.deepcopy(observation))
        # Skip Windows device construction, while retaining every production
        # check, binding comparison, input call, receipt, and artifact write.
        self.io = ProjectClosedLoopIO.__new__(ProjectClosedLoopIO)
        self.io.backend = self.backend
        self.io.reference = dict(baseline=copy.deepcopy(observation), instance_address=100,
                                 session_deadline_monotonic=100.)
        self.io.last_observation = copy.deepcopy(observation)
        self.io.folder = Path(self.folder.name)
        self.io.game = self.game
        self.io.original_game_check = self.game.check
        self.io.stop = threading.Event()
        self.io.f9_pressed = lambda: False
        self.io.deadline = 100.
        self.io.sent_any = False
        self.io.input_attempts = 0
        self.io.input_reference = None
        self.io._performing_input = False
        self.record = PointerGesture('drag', ((250, 250), (251, 250))).record()
        self.backend_record = dict(
            process_identity=[42, 11, 1000, 'build'], backend_object='0x100',
            backend_type='MM.Client.Framework.InputSystem.InputManager', input_assistant='0x0',
            legacy_mouse_getter_rva='0x185310', viewport_origin=[0, 0], viewport_scale=[1., 1.],
            observed_monotonic=10., inputs_sent=0, ready_for_input=False)
        self.backend_latency = 0.
        self.backend_reads = 0
        self.change_backend_at = None
        self.addCleanup(patch.stopall)
        patch('native_live.project_closed_loop_io.time.monotonic', self.clock.monotonic).start()
        patch('native_live.project_closed_loop_io.read_input_backend',
              side_effect=self.read_backend).start()

    def read_backend(self, *args, **kwargs):
        self.backend_reads += 1
        self.clock.now += self.backend_latency
        record = copy.deepcopy(self.backend_record)
        if self.backend_reads == self.change_backend_at:
            record['viewport_scale'] = [2., 2.]
        return record

    def protected(self, deadline=13.):
        method = getattr(self.io, 'perform_protected_candidate', None)
        self.assertTrue(callable(method), 'The protected phase entry point is missing')
        return method(self.record, 'protected', deadline)

    def assert_no_inputs(self):
        self.assertEqual(self.game.inputs, [])
        self.assertEqual(self.io.input_attempts, 0)
        self.assertFalse(self.io.sent_any)

    def test_ordinary_input_keeps_its_eight_second_feedback_reserve(self):
        with self.assertRaises(TimeoutError):
            self.io.perform_candidate(self.record, 'ordinary', 13.)
        self.assert_no_inputs()

    def test_protected_input_uses_the_reserved_short_phase(self):
        receipt = self.protected()
        self.assertTrue(receipt['completed'])
        self.assertEqual(len(self.game.inputs), 1)
        self.assertEqual(self.io.input_attempts, 1)
        self.assertLess(receipt['finished_monotonic'], 13.)
        self.assertFalse(self.io._performing_input)
        saved = json.loads((self.io.folder / 'protected.input.json').read_text())
        self.assertTrue(saved['completed'])

    def test_expired_protected_phase_never_sends_input(self):
        with self.assertRaises(TimeoutError):
            self.protected(deadline=10.)
        self.assert_no_inputs()

    def test_protected_phase_must_fit_the_actual_gesture_duration(self):
        with self.assertRaises(TimeoutError):
            self.protected(deadline=10.1)
        self.assert_no_inputs()

    def test_pre_input_reads_cannot_consume_the_gesture_time(self):
        self.backend_latency = .2
        with self.assertRaises(TimeoutError):
            self.protected(deadline=10.6)
        self.assert_no_inputs()

    def test_protected_input_rejects_a_backend_change_between_pre_input_reads(self):
        self.change_backend_at = 2
        with self.assertRaises(ValueError):
            self.protected()
        self.assert_no_inputs()

    def test_protected_input_rejects_a_changed_palette_binding(self):
        self.backend.observation['session_token'] = ['other-palette']
        with self.assertRaises(ValueError):
            self.protected()
        self.assert_no_inputs()

    def test_protected_input_rejects_a_changed_pre_input_pose(self):
        self.backend.observation['motion']['pose']['position'][0] = .01
        with self.assertRaises(ValueError):
            self.protected()
        self.assert_no_inputs()

    def test_protected_input_preserves_f9_stop(self):
        self.io.f9_pressed = lambda: True
        with self.assertRaises(InterruptedError):
            self.protected()
        self.assert_no_inputs()

    def test_pre_input_focus_wait_cannot_borrow_the_reserved_return_phase(self):
        from native_live.project_closed_loop_io import InputNotStarted

        def lost_focus():
            raise RuntimeError('游戏失去焦点')

        def pause(seconds):
            self.clock.now += seconds

        self.io.original_game_check = lost_focus
        with patch('native_live.project_probe_io.time.sleep', pause):
            with self.assertRaises(InputNotStarted):
                self.protected(deadline=10.4)
        self.assertAlmostEqual(self.clock.now, 10.4)
        self.assert_no_inputs()

    def test_unknown_protected_input_receipt_is_not_changed_to_completed(self):
        self.game.completed = False
        receipt = self.protected()
        self.assertFalse(receipt['completed'])
        self.assertEqual(len(self.game.inputs), 1)
        self.assertEqual(self.io.input_attempts, 1)
        self.assertFalse(self.io._performing_input)
        saved = json.loads((self.io.folder / 'protected.input.json').read_text())
        self.assertFalse(saved['completed'])


if __name__ == '__main__':
    unittest.main()
