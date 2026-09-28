import unittest
from types import SimpleNamespace
from unittest.mock import patch

from display_geometry import clamp_position, logical_size


class DisplayGeometryTests(unittest.TestCase):
    def test_clamp_keeps_negative_monitor_origin(self):
        self.assertEqual(clamp_position((-3000, -500), (-1920, -200, 5760, 2360), (820, 560)),
                         (-1920, -200))
        self.assertEqual(clamp_position((9999, 9999), (-1920, -200, 5760, 2360), (820, 560)),
                         (3020, 1600))

    def test_logical_size_uses_work_area_and_dpi(self):
        window = SimpleNamespace(_get_window_scaling=lambda: 2,
                                 winfo_id=lambda: 1,
                                 winfo_screenwidth=lambda: 1024,
                                 winfo_screenheight=lambda: 768)
        # On non-Windows fallback the native screen is 1024x768.
        with patch('display_geometry.work_area', return_value=(0, 0, 1024, 768)):
            self.assertEqual(logical_size(window, (660, 650), margins=(80, 100)), (432, 284))


if __name__ == '__main__':
    unittest.main()
