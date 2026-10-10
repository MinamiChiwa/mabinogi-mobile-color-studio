import unittest
import numpy as np


def zoom(scale, anchor):
    matrix = np.eye(3)
    matrix[:2, :2] *= scale
    matrix[:2, 2] = (1 - scale) * np.asarray(anchor)
    return matrix


class WheelMicroModelTests(unittest.TestCase):
    def test_nonreciprocal_pair_has_scale_residual(self):
        pair = zoom(.99, [265, 265]) @ zoom(1.01, [265, 265])
        self.assertAlmostEqual(pair[0, 0], .9999, places=7)
        self.assertAlmostEqual(pair[1, 1], .9999, places=7)
        self.assertGreater(np.linalg.norm(pair[:2, 2]), 0)

    def test_reciprocal_pair_is_identity_only_when_pivot_matches(self):
        same = zoom(1 / 1.01, [265, 265]) @ zoom(1.01, [265, 265])
        shifted = zoom(1 / 1.01, [266, 265]) @ zoom(1.01, [265, 265])
        np.testing.assert_allclose(same, np.eye(3), atol=1e-12)
        self.assertAlmostEqual(shifted[0, 2], 1 - 1 / 1.01, places=12)


if __name__ == '__main__':
    unittest.main()
