import unittest

from screen_mapping import image_point, screen_point


class ScreenMappingTests(unittest.TestCase):
    def test_one_to_one_mapping_preserves_physical_pixel(self):
        self.assertEqual(image_point(1279, 959, (1280, 960), (1280, 960)), (1279, 959))

    def test_scaled_canvas_maps_to_physical_capture(self):
        self.assertEqual(image_point(640, 480, (1280, 960), (2560, 1920)), (1280, 960))
        self.assertEqual(image_point(1279, 959, (1280, 960), (2560, 1920)), (2558, 1918))

    def test_mapping_clamps_events_at_canvas_edges(self):
        self.assertEqual(image_point(-10, 2000, (1280, 960), (2560, 1920)), (0, 1919))

    def test_screen_mapping_keeps_negative_virtual_desktop_origin(self):
        self.assertEqual(screen_point(640, 480, (1280, 960), (2560, 1920), (-1920, 40)), (-640, 1000))


if __name__ == '__main__':
    unittest.main()
