"""Read-only Win32 geometry when a target's client units are virtualized."""
import ctypes
import unittest

from native_live import read_dye_window as module


def _context_value(value):
    value = value.value if isinstance(value, ctypes.c_void_p) else value
    return value - (1 << 64) if value is not None and value >= (1 << 63) else value


class VirtualizedWindowAPI:
    """DPI-unaware 1280x960 client occupying 1920x1440 physical pixels."""
    def __init__(self):
        self.context = -2
        self.window_bounds = (-2020, 90, -80, 1570)
        self.client_origin = (-2010, 120)
        self.logical_screen_origin = (-1340, 80)
        self.api_size = (1280, 960)
        self.target_context_size = (1280, 960)
        self.client_coordinate_size = (1280, 960)
        self.physical_size = (1920, 1440)
        self.inverse_error = False
        self.fail_client_to_screen = False
        self.fail_logical_to_physical = False
        self.corner_error = False

    def SetThreadDpiAwarenessContext(self, value):
        previous = self.context
        self.context = _context_value(value)
        return previous

    def GetThreadDpiAwarenessContext(self):
        return self.context

    def AreDpiAwarenessContextsEqual(self, left, right):
        return _context_value(left) == _context_value(right)

    def GetWindowDpiAwarenessContext(self, hwnd):
        return -1

    def GetAwarenessFromDpiAwarenessContext(self, value):
        return 0

    def IsWindow(self, hwnd):
        return True

    def GetClientRect(self, hwnd, pointer):
        rect = pointer._obj
        rect.left = rect.top = 0
        rect.right, rect.bottom = self.target_context_size if self.context == -1 else self.api_size
        return True

    def GetWindowRect(self, hwnd, pointer):
        rect = pointer._obj
        rect.left, rect.top, rect.right, rect.bottom = self.window_bounds
        return True

    def ClientToScreen(self, hwnd, pointer):
        if self.fail_client_to_screen:
            return False
        point = pointer._obj
        if self.context == -1:
            point.x += self.logical_screen_origin[0]
            point.y += self.logical_screen_origin[1]
        else:
            point.x = self.client_origin[0] + round(point.x * self.physical_size[0] / self.client_coordinate_size[0])
            point.y = self.client_origin[1] + round(point.y * self.physical_size[1] / self.client_coordinate_size[1])
        return True

    def ScreenToClient(self, hwnd, pointer):
        point = pointer._obj
        if self.context == -1:
            point.x -= self.logical_screen_origin[0]
            point.y -= self.logical_screen_origin[1]
        else:
            point.x = round((point.x - self.client_origin[0]) * self.client_coordinate_size[0] / self.physical_size[0])
            point.y = round((point.y - self.client_origin[1]) * self.client_coordinate_size[1] / self.physical_size[1])
        if self.inverse_error:
            point.x += 1
        return True

    def LogicalToPhysicalPointForPerMonitorDPI(self, hwnd, pointer):
        if self.fail_logical_to_physical:
            return False
        point = pointer._obj
        top_right = (point.x - self.logical_screen_origin[0], point.y - self.logical_screen_origin[1]) == (1280, 0)
        point.x = self.client_origin[0] + round((point.x - self.logical_screen_origin[0]) * self.physical_size[0] / self.client_coordinate_size[0])
        point.y = self.client_origin[1] + round((point.y - self.logical_screen_origin[1]) * self.physical_size[1] / self.client_coordinate_size[1])
        if self.corner_error and top_right:
            point.x += 1
        return True

    def PhysicalToLogicalPointForPerMonitorDPI(self, hwnd, pointer):
        point = pointer._obj
        point.x = self.logical_screen_origin[0] + round((point.x - self.client_origin[0]) * self.client_coordinate_size[0] / self.physical_size[0])
        point.y = self.logical_screen_origin[1] + round((point.y - self.client_origin[1]) * self.client_coordinate_size[1] / self.physical_size[1])
        return True

    def MonitorFromWindow(self, hwnd, flags):
        return 1

    def GetMonitorInfoW(self, monitor, pointer):
        info = pointer._obj
        info.rcMonitor.left, info.rcMonitor.top, info.rcMonitor.right, info.rcMonitor.bottom = (-2560, 0, 0, 1600)
        info.rcWork.left, info.rcWork.top, info.rcWork.right, info.rcWork.bottom = (-2560, 0, 0, 1560)
        return True

    def DwmGetWindowAttribute(self, hwnd, attribute, pointer, size):
        rect = pointer._obj
        rect.left, rect.top, rect.right, rect.bottom = self.window_bounds
        return 0

    def GetWindowThreadProcessId(self, hwnd, pointer):
        pointer._obj.value = 2
        return 10

    def GetDpiForWindow(self, hwnd):
        return 96

    def IsWindowVisible(self, hwnd):
        return True

    def IsIconic(self, hwnd):
        return False

    def GetForegroundWindow(self):
        return 1

    def GetSystemMetrics(self, metric):
        return {76: -2560, 77: 0, 78: 5120, 79: 1600}[metric]


class HighDpiWindowReaderTests(unittest.TestCase):
    def reader(self, api=None):
        api = api or VirtualizedWindowAPI()
        reader = object.__new__(module._Win32WindowAPI)
        reader.u = reader.dwm = api
        return reader, api

    def test_virtualized_client_units_keep_the_measured_physical_extent(self):
        reader, api = self.reader()
        row = module.read_window_state(2, hwnd=1, api=reader)
        self.assertEqual(row['client_size_physical'], [1920, 1440])
        self.assertEqual(row['client_bounds_physical'], [-2010, 120, -90, 1560])
        self.assertEqual(row['client_origin_physical'], [-2010, 120])
        self.assertEqual(row['raw_client_rect'], [0, 0, 1280, 960])
        self.assertEqual(row['api_client_size'], [1280, 960])
        self.assertEqual(row['client_size_logical'], [1280, 960])
        self.assertEqual(row['window_dpi_awareness'], 0)
        self.assertTrue(row['coordinate_validation']['screen_to_client_roundtrip'])
        self.assertFalse(row['ready_for_input'])
        self.assertEqual(api.context, -2)

    def test_physical_reader_rect_does_not_become_target_client_coordinate_extent(self):
        reader, api = self.reader()
        api.api_size = (1920, 1440)
        row = module.read_window_state(2, hwnd=1, api=reader)
        self.assertEqual(row['raw_client_rect'], [0, 0, 1920, 1440])
        self.assertEqual(row['api_client_size'], [1920, 1440])
        self.assertEqual(row['client_size_in_window_dpi_context'], [1280, 960])
        self.assertEqual(row['client_size_physical'], [1920, 1440])
        self.assertEqual(row['client_bounds_physical'], [-2010, 120, -90, 1560])
        self.assertTrue(row['coordinate_validation']['screen_to_client_roundtrip'])
        self.assertEqual(api.context, -2)

    def test_target_hwnd_conversion_failure_keeps_raw_rect_and_restores_context(self):
        reader, api = self.reader()
        api.fail_logical_to_physical = True
        with self.assertRaises(ValueError) as caught:
            reader.snapshot(1)
        diagnostic = getattr(caught.exception, 'diagnostic', {})
        self.assertEqual(diagnostic.get('raw_client_rect'), [0, 0, 1280, 960])
        self.assertEqual(diagnostic.get('client_size_in_window_dpi_context'), [1280, 960])
        self.assertEqual(api.context, -2)

    def test_endpoint_extent_outside_window_is_rejected_with_measured_bounds(self):
        reader, api = self.reader()
        api.physical_size = (1921, 1440)
        api.window_bounds = (-2020, 90, -90, 1570)
        with self.assertRaises(ValueError) as caught:
            reader.snapshot(1)
        diagnostic = getattr(caught.exception, 'diagnostic', {})
        self.assertEqual(diagnostic.get('client_size_physical'), [1921, 1440])
        self.assertEqual(diagnostic.get('client_bounds_physical'), [-2010, 120, -89, 1560])
        self.assertEqual(diagnostic.get('window_bounds_physical'), [-2020, 90, -90, 1570])
        self.assertFalse(diagnostic.get('coordinate_validation', {}).get('client_within_window', True))
        self.assertEqual(api.context, -2)

    def test_inconsistent_inverse_conversion_is_rejected_with_raw_api_dimensions(self):
        reader, api = self.reader()
        api.inverse_error = True
        with self.assertRaises(ValueError) as caught:
            reader.snapshot(1)
        diagnostic = getattr(caught.exception, 'diagnostic', {})
        self.assertEqual(diagnostic.get('raw_client_rect'), [0, 0, 1280, 960])
        self.assertEqual(diagnostic.get('client_size_physical'), [1920, 1440])
        self.assertFalse(diagnostic.get('coordinate_validation', {}).get('screen_to_client_roundtrip', True))
        self.assertEqual(api.context, -2)

    def test_invalid_target_context_dimensions_retain_reader_candidate_geometry(self):
        reader, api = self.reader()
        api.target_context_size = (0, 960)
        with self.assertRaises(ValueError) as caught:
            reader.snapshot(1)
        diagnostic = getattr(caught.exception, 'diagnostic', {})
        self.assertEqual(diagnostic.get('client_size_from_reader_api'), [1920, 1440])
        self.assertEqual(diagnostic.get('client_size_in_window_dpi_context'), [0, 960])
        self.assertNotIn('client_size_physical', diagnostic)
        self.assertEqual(api.context, -2)

    def test_inconsistent_physical_corner_is_rejected_even_when_diagonal_is_correct(self):
        reader, api = self.reader()
        api.corner_error = True
        with self.assertRaises(ValueError) as caught:
            reader.snapshot(1)
        diagnostic = getattr(caught.exception, 'diagnostic', {})
        self.assertEqual(diagnostic.get('client_size_physical'), [1920, 1440])
        self.assertFalse(diagnostic.get('coordinate_validation', {}).get('physical_corners_axis_aligned', True))
        self.assertEqual(api.context, -2)

    def test_unstable_repeated_measurements_retain_both_physical_extents(self):
        reader, api = self.reader()
        class ResizingReader:
            count = 0
            def snapshot(self, hwnd):
                self.count += 1
                if self.count == 2:
                    api.physical_size = (1918, 1440)
                return reader.snapshot(hwnd)
        with self.assertRaises(ValueError) as caught:
            module.read_window_state(2, hwnd=1, api=ResizingReader())
        diagnostic = getattr(caught.exception, 'diagnostic', {})
        self.assertEqual(diagnostic.get('client_size_physical'), [1918, 1440])
        self.assertEqual([row['client_size_physical'] for row in diagnostic.get('window_measurements', [])],
                         [[1920, 1440], [1918, 1440]])
        self.assertEqual(api.context, -2)


if __name__ == '__main__':
    unittest.main()
