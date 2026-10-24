import unittest
from types import SimpleNamespace

import numpy as np

from atlas_masks import board_texture_mask, material_masks, mask_parameters


class AtlasMaskTests(unittest.TestCase):
    def scene(self):
        return SimpleNamespace(
            board=(100, 100, 600, 600),
            markers=[(183, 420), (350, 320), (517, 270)],
            cards=[(143, 0, 80, 80), (310, 0, 80, 80), (477, 0, 80, 80)],
        )

    def test_marker_connector_columns_are_masked_for_the_entire_board_height(self):
        scene = self.scene()
        mask = board_texture_mask(scene)
        self.assertEqual(mask.shape, (500, 500))
        for x, _y in np.asarray(scene.markers) - np.asarray(scene.board[:2]):
            self.assertFalse(mask[:, round(x)-18:round(x)+19].any())

    def test_each_material_keeps_its_own_full_height_connector_column_excluded(self):
        scene = self.scene()
        masks = material_masks(scene)
        self.assertEqual(masks.shape, (3, 500, 500))
        for index, (x, _y) in enumerate(np.asarray(scene.markers)-np.asarray(scene.board[:2])):
            self.assertFalse(masks[index, :, round(x)-18:round(x)+19].any())
            self.assertGreater(masks[index].sum(), 0)
        self.assertEqual(mask_parameters()['version'], 3)
        self.assertTrue(mask_parameters()['full_height_connector_columns'])

    def test_full_circle_corridor_is_invariant_to_marker_height(self):
        scene = self.scene()
        baseline = material_masks(scene)
        for heights in ((110, 300, 580), (590, 120, 400), (250, 500, 130)):
            scene.markers = [(x, y) for (x, _), y in zip(scene.markers, heights)]
            np.testing.assert_array_equal(material_masks(scene), baseline)

    def test_explicit_historical_corridor_preserves_ring_flanks(self):
        scene = self.scene()
        old = board_texture_mask(scene, stem_half_width=10)
        new = board_texture_mask(scene)
        self.assertFalse(new[:, 83+15].any())
        self.assertTrue(old[100, 83+15])
        self.assertFalse(old[320, 83+15])


if __name__ == '__main__':
    unittest.main()
