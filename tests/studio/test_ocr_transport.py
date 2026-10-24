import io
import unittest
from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired
from unittest.mock import patch

import numpy as np
from PIL import Image
import vision


class OcrTransportTests(unittest.TestCase):
    def test_unicode_data_path_is_one_unquoted_argument(self):
        data_dir = str(Path('C:/使用者/染色 工具/tessdata'))
        image = Image.new('RGB', (30, 12), 'white')
        result = CompletedProcess([], 0, b'#ABCDEF\r\n', b'')
        with patch('vision.subprocess.run', return_value=result) as process:
            text = vision._ocr_text(image, config=f'--tessdata-dir "{data_dir}" --psm 7', timeout=1.5)
        args = process.call_args.args[0]
        self.assertEqual(args[1:5], ['stdin', 'stdout', '-l', 'eng'])
        self.assertEqual(args[args.index('--tessdata-dir') + 1], data_dir)
        self.assertEqual(process.call_args.kwargs['timeout'], 1.5)
        self.assertEqual(text.strip(), '#ABCDEF')

    def test_ocr_pipe_preserves_image_pixels_without_temporary_paths(self):
        pixels = np.arange(36, dtype=np.uint8).reshape(3, 4, 3)
        with patch('vision.subprocess.run', return_value=CompletedProcess([], 0, b'123', b'')) as process:
            self.assertEqual(vision._ocr_text(pixels), '123')
        restored = np.asarray(Image.open(io.BytesIO(process.call_args.kwargs['input'])))
        np.testing.assert_array_equal(restored, pixels)
        self.assertEqual(process.call_args.args[0][1:3], ['stdin', 'stdout'])

    def test_localized_process_error_does_not_disable_next_frame(self):
        results = [CompletedProcess([], 1, b'', b'localized error: \xff'),
                   CompletedProcess([], 0, b'#AABBCC\n', b'')]
        with patch('vision.OCR_AVAILABLE', True), patch('vision.OCR_CONFIG', ''), \
             patch('vision.subprocess.run', side_effect=results):
            self.assertEqual(vision._tesseract(Image.new('RGB', (10, 10)), ''), '')
            self.assertTrue(vision.OCR_AVAILABLE)
            self.assertEqual(vision._tesseract(Image.new('RGB', (10, 10)), ''), '#AABBCC')

    def test_process_timeout_remains_recoverable(self):
        results = [TimeoutExpired('tesseract', 2), CompletedProcess([], 0, b'123', b'')]
        with patch('vision.OCR_AVAILABLE', True), patch('vision.OCR_CONFIG', ''), \
             patch('vision.subprocess.run', side_effect=results):
            self.assertEqual(vision._tesseract(Image.new('RGB', (10, 10)), ''), '')
            self.assertTrue(vision.OCR_AVAILABLE)
            self.assertEqual(vision._tesseract(Image.new('RGB', (10, 10)), ''), '123')


if __name__ == '__main__':
    unittest.main()
