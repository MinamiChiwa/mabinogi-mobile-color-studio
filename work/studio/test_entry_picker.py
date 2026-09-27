import unittest
from entry_picker import client_point,validate_entry_geometry


class EntryPointTests(unittest.TestCase):
    def test_screen_point_maps_to_client_coordinates_with_negative_origin(self):
        self.assertEqual(client_point((-1900, 120),(-1920,40,1280,960)),(20,80))

    def test_point_outside_game_client_is_rejected(self):
        for point in ((9,40),(1290,100),(100,1000)):
            with self.assertRaises(ValueError):client_point(point,(10,40,1280,960))

    def test_entry_must_match_current_client_size_and_remain_inside_bounds(self):
        self.assertEqual(validate_entry_geometry((1279,959),(1280,960),(-1920,0,1280,960)),(1280,960))
        with self.assertRaisesRegex(ValueError,'窗口尺寸已变化'):
            validate_entry_geometry((20,30),(1280,960),(-1920,0,1279,960))
        with self.assertRaisesRegex(ValueError,'超出游戏窗口'):
            validate_entry_geometry((1280,30),(1280,960),(-1920,0,1280,960))


if __name__=='__main__':unittest.main()
