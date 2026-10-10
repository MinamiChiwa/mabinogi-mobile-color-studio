import unittest
from types import SimpleNamespace
import numpy as np
from registration_precision_methods import board_masks, closure, ecc_translation


class RegistrationMethodTests(unittest.TestCase):
    def scene(self):
        return SimpleNamespace(board=(0, 0, 120, 120), markers=[(25, 80), (60, 50), (95, 82)])

    def test_material_masks_are_disjoint_and_nonempty(self):
        masks = board_masks(self.scene())
        self.assertEqual(masks.shape, (3, 120, 120))
        self.assertTrue(all(np.count_nonzero(row) for row in masks))
        self.assertEqual(np.count_nonzero(np.sum(masks > 0, axis=0) > 1), 0)

    def test_ecc_rejects_malformed_masks(self):
        image = np.zeros((120, 120, 3), np.uint8)
        with self.assertRaises(ValueError):
            ecc_translation(image, image, self.scene(), np.zeros((2, 2), np.uint8))
        with self.assertRaises(ValueError):
            ecc_translation(image, image, self.scene(), np.zeros((120, 120), np.uint8))

    def test_ecc_translation_returns_finite_matrix_on_textured_input(self):
        scene = self.scene()
        image = np.zeros((120, 120, 3), np.uint8)
        yy, xx = np.mgrid[:120, :120]
        image[..., 0] = ((xx * 7 + yy * 3) % 251).astype(np.uint8)
        image[..., 1] = ((xx * 5 + yy * 11) % 251).astype(np.uint8)
        image[..., 2] = ((xx * 13 + yy * 2) % 251).astype(np.uint8)
        shifted = np.roll(image, 1, axis=1)
        result = ecc_translation(image, shifted, scene, np.ones((120, 120), np.uint8) * 255)
        self.assertTrue(np.isfinite(result['matrix']).all())
        self.assertTrue(np.isfinite(result['score']))

    def test_closure_requires_both_matrices(self):
        points = [[0, 0], [10, 0], [20, 0]]
        self.assertIsNone(closure(None, None, points))

    def test_full_ecc_uses_runtime_texture_exclusion_by_default(self):
        scene = SimpleNamespace(board=(0, 0, 400, 400),
                                markers=[(80, 280), (200, 220), (320, 290)])
        image = np.zeros((400, 400, 3), np.uint8)
        yy, xx = np.mgrid[:400, :400]
        image[..., 0] = ((xx * 7 + yy * 3) % 251).astype(np.uint8)
        image[..., 1] = ((xx * 5 + yy * 11) % 251).astype(np.uint8)
        image[..., 2] = ((xx * 13 + yy * 2) % 251).astype(np.uint8)
        # A default mask is constructed internally; this smoke test only
        # requires the method to produce a finite result on a valid scene.
        result = ecc_translation(image, image, scene)
        self.assertEqual(result['translation'], [0., 0.])


if __name__ == '__main__':
    unittest.main()
