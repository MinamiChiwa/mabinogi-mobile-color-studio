import unittest
import numpy as np
from large_motion_review import overlap_counts


class LargeMotionReviewTests(unittest.TestCase):
    def setUp(self):
        self.masks = np.zeros((3, 50, 60), bool)
        for region in range(3):
            self.masks[region, 2:48, region * 20 + 2:region * 20 + 18] = True

    def test_board_overlap_does_not_imply_same_material_overlap(self):
        regions = overlap_counts(self.masks, [25, 0])
        board = overlap_counts(self.masks.any(axis=0)[None, ...], [25, 0])
        self.assertTrue(all(row['pixels'] == 0 for row in regions))
        self.assertGreater(board[0]['pixels'], 0)

    def test_short_horizontal_and_larger_vertical_moves_retain_texture(self):
        for translation in ([10, 0], [0, 35]):
            self.assertTrue(all(row['pixels'] > 0 for row in overlap_counts(self.masks, translation)))

    def test_overlap_requires_all_four_bilinear_neighbors(self):
        masks = np.zeros((1, 6, 6), bool)
        masks[0, 1:5, 1:5] = True
        self.assertEqual(overlap_counts(masks, [0, 0])[0]['pixels'], 9)
        masks[0, 2, 2] = False
        self.assertEqual(overlap_counts(masks, [0, 0])[0]['pixels'], 5)

    def test_empty_region_and_out_of_bounds_have_finite_zero_overlap(self):
        empty = overlap_counts(np.zeros_like(self.masks), [0, 0])
        far = overlap_counts(self.masks, [-1000, 1000])
        self.assertEqual(empty, far)
        self.assertTrue(all(row['fraction'] == 0. for row in empty))

    def test_malformed_mask_or_translation_is_rejected(self):
        for masks, delta in ((np.zeros((2, 2)), [0, 0]), (np.zeros((1, 1, 1)), [0, 0]),
                             (self.masks, [float('nan'), 0]), (self.masks, [1])):
            with self.assertRaises(ValueError):
                overlap_counts(masks, delta)


if __name__ == '__main__':
    unittest.main()
