"""Original UnityPlayer instruction outputs are the independent oracle."""
from test_support import read_local_fixture_text
import importlib
import importlib.util
import json
from pathlib import Path
import unittest

import numpy as np


class NativeTransformMatrixTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('native_transform_matrix'))
        self.m = importlib.import_module('native_transform_matrix')
        self.single = dict(positions=[[1, 2, 3]], quaternions_xyzw=[[0, 0, 0, 1]],
                           scales=[[1, 1, 1]], parents=[-1], index=0)

    def test_matches_complete_original_hierarchy_instructions(self):
        fixture = json.loads(read_local_fixture_text(Path(__file__).parent / 'fixtures/native_palette/transform_matrix_oracle.json'))
        self.assertEqual(len(fixture['cases']), 303)
        for i, case in enumerate(fixture['cases']):
            with self.subTest(case=i):
                args = {k: v for k, v in case.items() if k != 'original_matrix'}
                actual = self.m.local_to_world_matrix(**args)
                self.assertEqual(actual.dtype, np.float32)
                np.testing.assert_array_equal(actual, np.asarray(case['original_matrix'], dtype=np.float32))

    def test_parent_scale_applies_to_child_translation(self):
        matrix = self.m.local_to_world_matrix(positions=[[10, 20, 30], [1, 2, 3]],
            quaternions_xyzw=[[0, 0, 0, 1]] * 2, scales=[[2, 3, 4], [1, 1, 1]], parents=[-1, 0], index=1)
        np.testing.assert_array_equal(matrix, [[2, 0, 0, 12], [0, 3, 0, 26], [0, 0, 4, 42], [0, 0, 0, 1]])

    def test_only_selected_ancestry_contributes(self):
        matrix = self.m.local_to_world_matrix(positions=[[100, 0, 0], [1, 2, 3], [10, 0, 0]],
            quaternions_xyzw=[[0, 0, 0, 1]] * 3, scales=[[1, 1, 1]] * 3, parents=[-1, 2, -1], index=1)
        np.testing.assert_array_equal(matrix[:, 3], [11, 2, 3, 1])

    def test_cycle_and_out_of_range_parent_are_rejected(self):
        for parents in ([0], [1], [-2], [True], [0.5]):
            with self.subTest(parents=parents), self.assertRaises(ValueError):
                self.m.local_to_world_matrix(**dict(self.single, parents=parents))

    def test_selected_index_must_be_an_integer_in_range(self):
        for index in (-1, 1, True, 0.5):
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.m.local_to_world_matrix(**dict(self.single, index=index))

    def test_depth_limit_includes_selected_node(self):
        args = dict(positions=[[0, 0, 0]] * 3, quaternions_xyzw=[[0, 0, 0, 1]] * 3,
                    scales=[[1, 1, 1]] * 3, parents=[-1, 0, 1], index=2)
        with self.assertRaises(ValueError):
            self.m.local_to_world_matrix(**args, max_depth=2)
        np.testing.assert_array_equal(self.m.local_to_world_matrix(**args, max_depth=3), np.eye(4))
        for depth in (0, True, 0.5, 257):
            with self.assertRaises(ValueError):
                self.m.local_to_world_matrix(**self.single, max_depth=depth)

    def test_malformed_and_nonfinite_arrays_are_rejected(self):
        for change in (dict(positions=[]), dict(scales=[[1, 1]]), dict(parents=[]),
                       dict(positions=[[float('nan'), 0, 0]]), dict(scales=[[1, float('inf'), 1]]),
                       dict(quaternions_xyzw=[[0, 0, 0, float('nan')]])):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.m.local_to_world_matrix(**dict(self.single, **change))

    def test_zero_and_mirrored_scales_are_preserved(self):
        matrix = self.m.local_to_world_matrix(**dict(self.single, scales=[[-2, 0, 3]]))
        np.testing.assert_array_equal(matrix, [[-2, 0, 0, 1], [0, 0, 0, 2], [0, 0, 3, 3], [0, 0, 0, 1]])

    def test_float32_overflow_is_rejected(self):
        with self.assertRaises(ValueError):
            self.m.local_to_world_matrix(positions=[[0, 0, 0]] * 2, quaternions_xyzw=[[0, 0, 0, 1]] * 2,
                scales=[[3e38, 3e38, 3e38]] * 2, parents=[-1, 0], index=1)

    def test_cancellation_propagates(self):
        def stop():
            raise InterruptedError('cancelled')
        with self.assertRaises(InterruptedError):
            self.m.local_to_world_matrix(**self.single, check=stop)


if __name__ == '__main__':
    unittest.main()
