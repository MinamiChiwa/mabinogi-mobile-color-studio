"""Physical capture/input coordinates when the caller inherited virtual DPI units."""
import ctypes
import importlib
import importlib.util
import threading
import unittest
from unittest.mock import patch

from PIL import Image
import platform_win as win
from input_gestures import wheel_gesture
from window_target import WindowTarget


def _context_value(value):
    value = value.value if isinstance(value, ctypes.c_void_p) else value
    return value - (1 << 64) if value is not None and value >= (1 << 63) else value


class VirtualizedAPI:
    """150% caller virtualization; native PMv2 operations return physical pixels."""
    def __init__(self):
        self.context = -2
        self.fail_enter = self.fail_restore = self.wrong_context = False
        self.metrics_contexts = []
        self.cursor_contexts = []

    def SetThreadDpiAwarenessContext(self, requested):
        requested = _context_value(requested)
        if requested == -4 and self.fail_enter:
            return None
        if requested == -2 and self.fail_restore:
            return None
        previous = self.context
        self.context = -2 if self.wrong_context and requested == -4 else requested
        return previous

    def GetThreadDpiAwarenessContext(self):
        return self.context

    def AreDpiAwarenessContextsEqual(self, a, b):
        return _context_value(a) == _context_value(b)

    def IsIconic(self, hwnd):
        return False

    def GetWindowDpiAwarenessContext(self,hwnd):return -1

    def LogicalToPhysicalPointForPerMonitorDPI(self,hwnd,pointer):
        point=pointer._obj;point.x=round(point.x*1.5);point.y=round(point.y*1.5);return True

    def GetClientRect(self, hwnd, pointer):
        rect = pointer._obj
        rect.left = rect.top = 0
        rect.right, rect.bottom = (1280, 960) if self.context == -4 else (853, 640)
        return True

    def ClientToScreen(self, hwnd, pointer):
        point = pointer._obj
        origin=(-1920,120) if self.context==-4 else (-1280,80)
        point.x,point.y=point.x+origin[0],point.y+origin[1]
        return True

    def GetSystemMetrics(self, metric):
        self.metrics_contexts.append(self.context)
        return ({76: -1920, 77: 0, 78: 5760, 79: 2160} if self.context == -4 else
                {76: -1280, 77: 0, 78: 3840, 79: 1440})[metric]

    def GetCursorPos(self, pointer):
        self.cursor_contexts.append(self.context)
        pointer._obj.x, pointer._obj.y = (-1800, 300) if self.context == -4 else (-1200, 200)
        return True


class PhysicalPlatformTests(unittest.TestCase):
    def setUp(self):
        self.api = VirtualizedAPI()
        self.game = win.Game.__new__(win.Game)
        self.game.target = WindowTarget(1, 2, 'Game')
        self.game.hwnd = 1
        self.game.stop = threading.Event()
        self.enterContext(patch.object(win, 'u', self.api))
        self.enterContext(patch.object(win, 'valid_target', return_value=True))
        if importlib.util.find_spec('window_dpi') is not None:
            module = importlib.import_module('window_dpi')
            self.enterContext(patch.object(module, '_u', self.api))

    def test_geometry_uses_physical_client_and_preserves_negative_origin(self):
        self.assertEqual(self.game.geometry(), (-1920, 120, 1280, 960))
        self.assertEqual(self.api.context, -2)

    def test_geometry_uses_screen_endpoints_when_client_api_units_are_scaled(self):
        original=self.api.ClientToScreen
        client=self.api.GetClientRect
        def target_rect(hwnd,pointer):
            if self.api.context==-1:
                r=pointer._obj;r.left=r.top=0;r.right,r.bottom=1280,960;return True
            return client(hwnd,pointer)
        self.api.GetClientRect=target_rect
        def scaled(hwnd,pointer):
            point=pointer._obj
            if self.api.context==-4:
                point.x,point.y=round(point.x*1.5)-1920,round(point.y*1.5)+120
                return True
            return original(hwnd,pointer)
        self.api.ClientToScreen=scaled
        self.assertEqual(self.game.geometry(),(-1920,120,1920,1440))
        self.assertEqual(self.api.context,-2)

    def test_geometry_uses_target_awareness_units_when_reader_rect_is_physical(self):
        original=self.api.GetClientRect
        def client(hwnd,pointer):
            if self.api.context==-1:
                r=pointer._obj;r.left=r.top=0;r.right,r.bottom=1280,960;return True
            return original(hwnd,pointer)
        self.api.GetClientRect=client
        self.api.ClientToScreen=lambda hwnd,p: self._target_to_screen(p)
        self.assertEqual(self.game.geometry(),(-1920,120,1920,1440))
        self.assertEqual(self.api.context,-2)

    def _target_to_screen(self,pointer):
        point=pointer._obj
        origin=(-1280,80) if self.api.context==-1 else (-1920,120)
        point.x+=origin[0];point.y+=origin[1];return True

    def test_capture_uses_physical_bbox_inside_physical_context(self):
        self.game.check = lambda: None
        seen = []
        def grab(*, bbox, all_screens):
            seen.append((bbox, all_screens, self.api.context))
            return Image.new('RGB', (bbox[2] - bbox[0], bbox[3] - bbox[1]))
        with patch.object(win.ImageGrab, 'grab', side_effect=grab):
            image = self.game.capture()
        self.assertEqual(image.shape, (960, 1280, 3))
        self.assertEqual(seen, [((-1920, 120, -640, 1080), True, -4)])
        self.assertEqual(self.api.context, -2)

    def test_absolute_move_uses_same_physical_virtual_desktop_units(self):
        sent = []
        self.game.send = lambda *args: sent.append((args, self.api.context))
        self.game.move_to((120, 180))
        self.assertEqual(sent, [((0xC001, 1366, 9106), -4)])
        self.assertEqual(self.api.metrics_contexts, [-4] * 4)
        self.assertEqual(self.api.context, -2)

    def test_cursor_trace_subtracts_physical_origin_from_physical_cursor(self):
        self.game.check = lambda: None
        self.game.move_to = lambda point: None
        self.game.send = lambda *args, **kwargs: None
        self.game.capture_input_trace = True
        with patch.object(win.time, 'sleep'):
            self.game.perform_gesture(wheel_gesture((0, 0, 500, 500), 1, (120, 180)))
        self.assertEqual(self.game.last_input_trace[0]['actual_client'], [120, 180])
        self.assertEqual(self.api.cursor_contexts, [-4])
        self.assertEqual(self.api.context, -2)

    def test_capture_failure_restores_callers_context(self):
        self.game.check = lambda: None
        with patch.object(win.ImageGrab, 'grab', side_effect=OSError('capture failed')):
            with self.assertRaisesRegex(OSError, 'capture failed'):
                self.game.capture()
        self.assertEqual(self.api.context, -2)

    def test_capture_enters_overlay_exclusion_scope_inside_physical_context(self):
        from contextlib import contextmanager
        seen=[];self.game.check=lambda:None
        @contextmanager
        def scope():
            seen.append(('enter',self.api.context))
            try:yield
            finally:seen.append(('exit',self.api.context))
        def grab(*,bbox,all_screens):
            seen.append(('capture',self.api.context));return Image.new('RGB',(1280,960))
        with patch.object(win,'capture_scope',scope,create=True),patch.object(win.ImageGrab,'grab',side_effect=grab):
            self.game.capture()
        self.assertEqual(seen,[('enter',-4),('capture',-4),('exit',-4)])
        self.assertEqual(self.api.context,-2)

    def test_failed_physical_context_never_captures_virtualized_image(self):
        self.api.fail_enter = True
        self.game.check = lambda: None
        with patch.object(win.ImageGrab, 'grab') as capture:
            with self.assertRaises(OSError):
                self.game.capture()
        capture.assert_not_called()
        self.assertEqual(self.api.context, -2)


class PhysicalContextTests(unittest.TestCase):
    def context(self, api):
        self.assertIsNotNone(importlib.util.find_spec('window_dpi'), 'Physical DPI context helper missing')
        return importlib.import_module('window_dpi').physical_pixel_context(api)

    def test_nested_contexts_restore_the_outer_then_original_context(self):
        api = VirtualizedAPI()
        with self.context(api):
            self.assertEqual(api.context, -4)
            with self.context(api):
                self.assertEqual(api.context, -4)
            self.assertEqual(api.context, -4)
        self.assertEqual(api.context, -2)

    def test_unconfirmed_context_is_rejected_and_restored(self):
        api = VirtualizedAPI(); api.wrong_context = True
        with self.assertRaises(OSError):
            with self.context(api):
                self.fail('Unconfirmed physical coordinates reached caller')
        self.assertEqual(api.context, -2)

    def test_failed_restore_is_reported(self):
        api = VirtualizedAPI(); api.fail_restore = True
        with self.assertRaises(OSError):
            with self.context(api):
                pass


if __name__ == '__main__':
    unittest.main()
