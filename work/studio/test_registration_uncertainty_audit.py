import unittest
from types import SimpleNamespace
import numpy as np
from registration_uncertainty_audit import displacement, summarize_pair, sift_variant


class RegistrationUncertaintyTests(unittest.TestCase):
    def scene(self):
        return SimpleNamespace(board=(0, 0, 400, 400), markers=[(80, 280), (200, 220), (320, 290)])

    def test_displacement_reports_marker_specific_affine_error(self):
        matrix = [[1.001, 0, .2], [0, 1.001, -.1]]
        rows = displacement(matrix, [[0, 0], [100, 0], [200, 0]])
        np.testing.assert_allclose(rows, [[.2, -.1], [.3, -.1], [.4, -.1]])

    def test_pair_summary_counts_only_bidirectional_variants(self):
        forward = [dict(variant='a', matrix=[[1, 0, .1], [0, 1, 0]]),
                   dict(variant='b', matrix=[[1, 0, .2], [0, 1, 0]])]
        reverse = {'a': dict(variant='a', matrix=[[1, 0, -.1], [0, 1, 0]])}
        result = summarize_pair(forward, reverse, [[0, 0], [10, 0], [20, 0]])
        self.assertEqual(result['variant_count'], 1)
        self.assertEqual(result['forward_marker_range_max'], 0.)

    def test_sift_rejects_invalid_diagnostic_parameters(self):
        image = np.zeros((400, 400, 3), np.uint8)
        with self.assertRaises(ValueError):
            sift_variant(image, image, self.scene(), ratio=.4)
        with self.assertRaises(ValueError):
            sift_variant(image, image, self.scene(), ransac=9)


if __name__ == '__main__':
    unittest.main()
