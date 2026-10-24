import unittest
from types import SimpleNamespace

from palette_viewer import initial_palette_size
from search_overlay import clamp_surface_position,clamp_virtual_surface_position
from ui_dialogs import logical_screen_limit
from window_picker import initial_picker_size


class DpiLayoutTests(unittest.TestCase):
    def _window(self, screen, scale):
        return SimpleNamespace(
            winfo_screenwidth=lambda: screen[0],
            winfo_screenheight=lambda: screen[1],
            _get_window_scaling=lambda: scale,
        )

    def test_dialog_size_uses_logical_dimensions_at_200_percent(self):
        # 1024x768 physical at 200% leaves 432x284 logical after margins.
        self.assertEqual(logical_screen_limit(self._window((1024, 768), 2), (660, 650)), (432, 284))

    def test_palette_and_picker_never_exceed_high_dpi_screen(self):
        window = self._window((1024, 768), 2)
        self.assertEqual(initial_palette_size(window), (412, 284))
        self.assertEqual(initial_picker_size(window), (432, 284))

    def test_saved_overlay_position_is_clamped_using_native_surface_size(self):
        # Surface is 820x560 physical after CTk scales 410x280 logical at 2x.
        self.assertEqual(clamp_surface_position((9999, 9999), (3840, 2160), (820, 560)), (3020, 1600))
        self.assertEqual(clamp_surface_position((-30, -2), (3840, 2160), (820, 560)), (0, 0))

    def test_overlay_can_remain_on_negative_virtual_monitor(self):
        self.assertEqual(
            clamp_virtual_surface_position((-1800, 20), (-1920, -200, 5760, 2360), (820, 560)),
            (-1800, 20),
        )
        self.assertEqual(
            clamp_virtual_surface_position((9999, 9999), (-1920, -200, 5760, 2360), (820, 560)),
            (3020, 1600),
        )


if __name__ == '__main__':
    unittest.main()
