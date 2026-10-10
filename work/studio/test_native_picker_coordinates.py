import json
import unittest
from pathlib import Path
import numpy as np
from native_palette_model import picker_view_uv, distort_cpu_uv
from test_support import requires_local_fixture


class NativePickerCoordinateTests(unittest.TestCase):
    def test_original_instruction_coordinates_at_all_42_client_points(self):
        path = Path(__file__).parent / 'fixtures' / 'native_palette' / 'picker_coordinate_oracle.json'
        requires_local_fixture(path)
        record = json.loads(path.read_text())
        self.assertEqual(len(record['cases']), 42)
        self.assertEqual(record['max_native_client_error'], 0)
        for case in record['cases']:
            with self.subTest(snapshot=case['snapshot'], index=case['index']):
                uv = picker_view_uv(case['index'], case['count'], case['picker_y'],
                                    case['position'], case['scale'], case['rotation_degrees'])
                np.testing.assert_array_equal(uv, np.array(case['native_view_uv'], np.float32))
                np.testing.assert_array_equal(distort_cpu_uv(uv), np.array(case['native_distorted_uv'], np.float32))


if __name__ == '__main__':
    unittest.main()
