import unittest
import numpy as np
from micro_registration_review import marker_error, homogeneous


class RegistrationAuditTests(unittest.TestCase):
    def test_marker_error_exposes_scale_at_separated_points(self):
        matrix = np.eye(3)
        matrix[:2, :2] *= 1.001
        errors = marker_error(matrix, np.eye(3), [[0, 0], [100, 0], [200, 0]])
        np.testing.assert_allclose(errors, [0, .1, .2])

    def test_exact_inverse_closure_does_not_prove_forward_accuracy(self):
        wrong = np.eye(3)
        wrong[0, 2] = 1.
        points = [[0, 0], [100, 0], [200, 0]]
        self.assertEqual(marker_error(np.linalg.inv(wrong) @ wrong, np.eye(3), points), [0., 0., 0.])
        self.assertEqual(marker_error(wrong, np.eye(3), points), [1., 1., 1.])

    def test_malformed_affine_is_rejected(self):
        with self.assertRaises(ValueError):
            homogeneous(dict(matrix=[[1, 0, float('nan')], [0, 1, 0]]))


if __name__ == '__main__':
    unittest.main()
