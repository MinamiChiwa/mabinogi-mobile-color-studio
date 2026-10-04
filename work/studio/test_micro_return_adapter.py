import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from contextlib import contextmanager
import unittest
from unittest.mock import patch
import numpy as np
from micro_return_adapter import MicroReturnAdapter, run_prepared_diagnostic
from workflow_budget import WorkflowBudget
from test_support import SimulatedReturnAdapter
from analyze_live_atlas import frame_sequence


class FakeGame:
    def __init__(self):
        self.sim = SimulatedReturnAdapter()
        self.until = 60.
        self.stage_until = 50.
        self.initial = (10, 20, 400, 400)
        self.scopes = []
        self.events = []
        self.after_move = lambda: None
        self.images = {}
        self.fail_left_release = False

    def geometry(self):
        return self.initial

    def check(self):
        self.sim.check()
        if self.sim.now >= min(self.until, self.stage_until):
            raise RuntimeError('Game deadline')

    @contextmanager
    def input_scope(self, deadline, guard):
        self.scopes.append((deadline, guard))
        try:
            yield
        finally:
            self.scopes.pop()

    def boundary(self):
        self.check()
        for deadline, guard in self.scopes:
            if self.sim.now >= deadline:
                raise RuntimeError('Final input deadline')
            guard()

    def move_to(self, anchor):
        self.boundary()
        self.events.append(('move', list(anchor)))
        self.after_move()

    def wheel(self, board, notch, anchor):
        self.move_to(anchor)
        self.boundary()
        self.sim.wheel(notch, np.asarray(anchor) - board[:2], deadline=self.until, guard=self.boundary)
        self.events.append(('wheel', notch))

    def pause(self, seconds):
        self.sim.pause(seconds)

    def capture(self):
        self.check()
        image = np.full((400, 400, 3), len(self.images), np.uint8)
        self.images[id(image)] = (image, self.sim.pose.copy())
        self.sim.now += .05
        return image

    def send(self, flag):
        self.events.append(('send', flag))
        if flag == 4 and self.fail_left_release:
            raise RuntimeError('left release failed')


class PreparedAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.g = FakeGame()
        self.scene = SimpleNamespace(board=(100, 100, 300, 300),
                                     markers=[(135, 250), (200, 210), (265, 260)],
                                     cards=[(120, 70, 30, 20), (185, 70, 30, 20), (250, 70, 30, 20)])
        self.configure = self.enterContext(patch('micro_return_adapter.configure_ocr'))
        self.recognize = self.enterContext(patch('micro_return_adapter.recognize', side_effect=self.recognized))
        self.enterContext(patch('micro_return_adapter.registered_motion', side_effect=self.motion))

    def recognized(self, image, **kwargs):
        self.g.sim.now += .4
        return SimpleNamespace(**vars(self.scene), seconds=100, colors=['#123456', '#789ABC', '#DEF012'])

    def motion(self, a, b, scene):
        transform = self.g.images[id(b)][1] @ np.linalg.inv(self.g.images[id(a)][1])
        return dict(matrix=transform[:2].tolist(), scale=float(transform[0, 0]), angle=0.)

    def adapter(self):
        return MicroReturnAdapter(self.g, self.scene, WorkflowBudget(0., 100.), Path(self.temp.name)/'run',
                                  session='test-session', clock=lambda: self.g.sim.now)

    def anchors(self):
        return {'x': [[200, 200], [224, 200]], 'y': [[200, 200], [200, 224]]}

    def baseline(self, adapter):
        adapter.begin(25.)
        for name in ('baseline_0', 'baseline_1'):
            adapter.read_codes(adapter.capture(name))

    def test_full_fake_run_preserves_images_codes_budget_and_crop_coordinates(self):
        a = self.adapter()
        self.assertEqual(self.g.events, [])
        np.testing.assert_array_equal(a.marker_points(), [[35, 150], [100, 110], [165, 160]])
        result = run_prepared_diagnostic(a, self.anchors())
        self.assertTrue(result['protocol_passed'], result['error'])
        self.assertFalse(result['registration_uncertainty_validated'])
        self.assertFalse(result['production_ready'])
        self.assertEqual(len(self.g.sim.wheels), 8)
        self.assertEqual(self.g.until, 60.)
        self.assertEqual(self.g.stage_until, 50.)
        self.assertEqual(a.until, 50.)
        self.assertEqual(len(list(a.folder.glob('*.png'))), 20)
        self.assertEqual(json.loads((a.folder/'return-result.json').read_text())['axes_completed'], ['x', 'y'])
        self.assertEqual(len([r for r in a.events if r['kind']=='micro_return_ocr']), 10)
        self.assertEqual(self.g.scopes, [])
        self.configure.assert_called_once_with(strict=True)
        with self.assertRaisesRegex(ValueError, 'not atlas'):
            frame_sequence(a.events)

    def test_final_boundary_stops_wheel_after_cursor_move(self):
        a = self.adapter()
        self.baseline(a)
        self.g.after_move = lambda: setattr(self.g.sim, 'stopped', True)
        with self.assertRaises(RuntimeError):
            a.wheel(1, [200, 200], deadline=20., guard=lambda: None)
        self.assertEqual(self.g.sim.wheels, [])
        self.assertEqual(self.g.scopes, [])

    def test_final_boundary_enforces_reserve_without_changing_existing_deadlines(self):
        a = self.adapter()
        self.baseline(a)
        self.g.after_move = lambda: setattr(self.g.sim, 'now', 20.)
        with self.assertRaisesRegex(RuntimeError, 'deadline'):
            a.wheel(1, [200, 200], deadline=20., guard=lambda: None)
        self.assertEqual(self.g.sim.wheels, [])
        self.assertEqual((self.g.until, self.g.stage_until), (60., 50.))

    def test_missing_timer_or_changed_geometry_stops_before_wheel(self):
        for kind in ('timer', 'geometry', 'hex'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as folder:
                a = MicroReturnAdapter(self.g, self.scene, WorkflowBudget(0., 100.), Path(folder)/'run',
                                       session='test', clock=lambda: self.g.sim.now)
                record = self.recognized(None)
                if kind == 'timer':
                    record.seconds = None
                elif kind == 'geometry':
                    record.board = (101, 100, 301, 300)
                else:
                    record.colors = [None]*3
                self.recognize.side_effect = None
                self.recognize.return_value = record
                result = run_prepared_diagnostic(a, self.anchors())
                self.assertFalse(result['protocol_passed'])
                self.assertFalse(result['current_verified'])
                self.assertEqual(self.g.sim.wheels, [])
                self.assertTrue((a.folder/'return-result.json').exists())

    def test_countdown_can_only_tighten_shared_budget(self):
        a = self.adapter()
        a.begin(25.)
        im = a.capture('baseline_0')
        record = self.recognized(im)
        record.seconds = 5
        self.recognize.side_effect = None
        self.recognize.return_value = record
        a.read_codes(im)
        shortened = a.until
        self.assertLess(shortened, 6.)
        record.seconds = 120
        a.read_codes(a.capture('baseline_1'))
        self.assertEqual(a.until, shortened)

    def test_reusing_one_image_or_unknown_image_is_rejected(self):
        a = self.adapter()
        a.begin(25.)
        im = a.capture('baseline_0')
        a.read_codes(im)
        with self.assertRaisesRegex(RuntimeError, 'independent'):
            a.read_codes(im)
        with self.assertRaises(ValueError):
            a.read_codes(im.copy())
        with self.assertRaises(ValueError):
            a.capture('baseline_0')
        with self.assertRaises(ValueError):
            a.capture('../outside')

    def test_capture_cannot_move_cursor_before_begin(self):
        a = self.adapter()
        with self.assertRaisesRegex(RuntimeError, 'not begun'):
            a.capture('baseline_0')
        self.assertEqual(self.g.events, [])

    def test_journal_delay_cannot_publish_expired_current_state(self):
        a = self.adapter()
        original = a.log
        def slow(kind, **fields):
            original(kind, **fields)
            if kind == 'micro_return_finished':
                self.g.sim.now = 26.
        a.log = slow
        result = run_prepared_diagnostic(a, self.anchors())
        self.assertFalse(result['current_verified'])
        self.assertFalse(result['protocol_passed'])
        self.assertEqual(result['axes_completed'], ['x', 'y'])
        self.assertFalse(json.loads((a.folder/'return-result.json').read_text())['current_verified'])

    def test_no_wheel_without_verified_double_baseline(self):
        a = self.adapter()
        a.begin(25.)
        with self.assertRaisesRegex(RuntimeError, 'baseline'):
            a.wheel(1, [200, 200], deadline=20., guard=lambda: None)
        self.assertEqual(self.g.sim.wheels, [])

    def test_changed_window_and_unsafe_anchor_block_input(self):
        a = self.adapter()
        self.baseline(a)
        with self.assertRaises(ValueError):
            a.wheel(1, [100, 200], deadline=20., guard=lambda: None)
        self.g.initial = (11, 20, 400, 400)
        with self.assertRaisesRegex(RuntimeError, 'geometry'):
            a.wheel(1, [200, 200], deadline=20., guard=lambda: None)
        self.assertEqual(self.g.sim.wheels, [])

    def test_inconsistent_reverse_registration_stops_before_wheel(self):
        a = self.adapter()
        original = self.motion
        calls = [0]
        def inconsistent(first, second, scene):
            calls[0] += 1
            result = original(first, second, scene)
            if calls[0] % 2 == 0:
                result['matrix'][0][2] += .06
            return result
        with patch('micro_return_adapter.registered_motion', side_effect=inconsistent):
            result = run_prepared_diagnostic(a, self.anchors())
        self.assertEqual(self.g.sim.wheels, [])
        self.assertFalse(result['protocol_passed'])
        self.assertIn('Bidirectional', result['error'])
        diagnostic = next(e for e in a.events if e['kind'] == 'micro_return_bidirectional_motion')
        self.assertGreater(max(diagnostic['closure_pixels']), .035)

    def test_single_use_prevents_automatic_retry(self):
        a = self.adapter()
        run_prepared_diagnostic(a, self.anchors())
        with self.assertRaisesRegex(RuntimeError, 'single use'):
            run_prepared_diagnostic(a, self.anchors())
        self.assertEqual(len(self.g.sim.wheels), 8)

    def test_release_attempts_both_buttons_even_if_first_fails(self):
        a = self.adapter()
        self.g.fail_left_release = True
        with self.assertRaises(RuntimeError):
            a.release()
        self.assertEqual(self.g.events[-2:], [('send', 4), ('send', 16)])

    def test_requires_existing_deadline_and_guard_bridge(self):
        self.g.until = float('inf')
        with self.assertRaisesRegex(ValueError, 'deadline'):
            self.adapter()
        self.assertEqual(self.g.events, [])


if __name__ == '__main__':
    unittest.main()
