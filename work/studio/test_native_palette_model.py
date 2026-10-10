from test_support import read_local_fixture_text
import unittest
import json
import hashlib
from pathlib import Path
import numpy as np
from test_support import requires_local_fixture
from PIL import Image

from native_palette_model import (
    color32,
    distort_uv,
    sample_cpu,
    view_uv,
    predict_hex,
)


class NativePaletteModelTests(unittest.TestCase):
    def test_cpu_sampling_uses_bottom_up_repeat_bilinear(self):
        # Top row is red/green; bottom row is blue/white in saved top-down form.
        pixels = np.array([
            [[255, 0, 0], [0, 255, 0]],
            [[0, 0, 255], [255, 255, 255]],
        ], dtype=np.uint8)
        value = sample_cpu(pixels, np.array([[0.25, 0.25]], np.float32), 0.0)[0]
        np.testing.assert_array_equal(value, [0, 0, 255])
        mixed = sample_cpu(pixels, [[0.5, 0.5]], 0.0)[0]
        np.testing.assert_allclose(mixed, [127.5, 127.5, 127.5], atol=1e-5)
        repeated = sample_cpu(pixels, [[1.25, -0.75]], 0.0)[0]
        np.testing.assert_array_equal(repeated, value)

    def test_view_and_distortion_are_float32_and_periodic(self):
        uv = np.array([[0.17, 0.83], [1.17, -0.17]], np.float32)
        coordinates = view_uv(uv, [0.02, -0.03], 1.2, 17.0)
        self.assertEqual(coordinates.dtype, np.float32)
        base = distort_uv(coordinates)
        shifted = distort_uv(coordinates + 1.0)
        np.testing.assert_allclose(base, shifted - 1.0, atol=3e-6)

    def test_captured_client_colors_at_all_recorded_poses(self):
        root = Path(__file__).parent / 'fixtures' / 'native_palette'
        manifest = json.loads(read_local_fixture_text(root / 'manifest.json', encoding='utf-8'))
        requires_local_fixture(*(root / name for name in manifest['file_sha256']))
        for name, digest in manifest['file_sha256'].items():
            self.assertEqual(hashlib.sha256((root / name).read_bytes()).hexdigest(), digest)
        count = 0
        for name in manifest['snapshots']:
            folder = root / name
            snapshot = json.loads(read_local_fixture_text(folder / 'snapshot.json', encoding='utf-8'))
            n = len(snapshot['fragments'])
            for index, fragment in enumerate(snapshot['fragments']):
                with self.subTest(snapshot=name, region=index):
                    pixels = np.asarray(Image.open(folder / fragment['pixel_file']).convert('RGB'))
                    uv = [(index + .5) / n, fragment['normalized_picker_y']]
                    transformed = distort_uv(view_uv(uv, snapshot['position'], snapshot['scale'], snapshot['rotation_degrees']))
                    predicted = sample_cpu(pixels, transformed, snapshot['color_preserve_ratio']) / np.float32(255)
                    client = snapshot['picker_colors_rgba'][index][:3]
                    np.testing.assert_allclose(predicted, client, rtol=0, atol=1e-5)
                    np.testing.assert_array_equal(color32(predicted), color32(client))
                    expected_hex = '#%02X%02X%02X' % tuple(int(x) for x in color32(client))
                    self.assertEqual(predict_hex(pixels, transformed, snapshot['color_preserve_ratio']), expected_hex)
                    count += 1
        self.assertEqual(count, manifest['client_color_count'])
        self.assertGreaterEqual(count, 27)

    def test_original_instruction_quantization_cases(self):
        root = Path(__file__).parent / 'fixtures' / 'native_palette'
        record = json.loads(read_local_fixture_text(root / 'native_quantization.json', encoding='utf-8'))
        self.assertEqual(record['cases'], 769)
        for case in record['details']:
            with self.subTest(value=case['input']):
                actual = color32([case['input']] * 3 + [1.]).tolist() if 'byte_base' in case else color32([case['input']] * 4).tolist()
                self.assertEqual(actual, case['actual'])

    def test_color32_matches_game_rounding_boundary(self):
        values = np.array([(127.5 / 255), (128.5 / 255), 0.0, 1.0], np.float32)
        np.testing.assert_array_equal(color32(values), [128, 128, 0, 255])

    def test_p_one_is_rejected(self):
        pixels = np.zeros((2, 2, 3), np.uint8)
        with self.assertRaises(ValueError):
            sample_cpu(pixels, [[0.1, 0.2]], 1.0)


if __name__ == '__main__':
    unittest.main()
