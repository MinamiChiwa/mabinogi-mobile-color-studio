import unittest
from unittest.mock import patch
import numpy as np
import vision
import json
from pathlib import Path
from PIL import Image


class OcrSetupTests(unittest.TestCase):
    def setUp(self):
        self.old_state=vision.OCR_AVAILABLE
        self.old_command=vision.pytesseract.pytesseract.tesseract_cmd
        self.addCleanup(setattr,vision,'OCR_AVAILABLE',self.old_state)
        self.addCleanup(setattr,vision.pytesseract.pytesseract,'tesseract_cmd',self.old_command)

    def test_project_local_ocr_is_found_after_moving_checkout(self):
        expected=vision.Path(vision.__file__).resolve().parents[2]/'outputs/dependencies/ocr/tesseract.exe'
        with patch.object(vision.Path,'is_file',autospec=True,side_effect=lambda p:p==expected), \
             patch('vision.pytesseract.get_tesseract_version'), \
             patch('vision.pytesseract.get_languages',return_value=['eng']):
            self.assertTrue(vision.configure_ocr(strict=True))
        self.assertEqual(vision.pytesseract.pytesseract.tesseract_cmd,str(expected))
        self.assertTrue(vision.OCR_AVAILABLE)

    def test_missing_english_data_blocks_formal_capture(self):
        with patch.object(vision.Path,'is_file',return_value=True), \
             patch('vision.pytesseract.get_tesseract_version'), \
             patch('vision.pytesseract.get_languages',return_value=[]):
            with self.assertRaisesRegex(RuntimeError,'文字识别'):
                vision.configure_ocr(strict=True)
        self.assertFalse(vision.OCR_AVAILABLE)

    def test_missing_executable_blocks_formal_capture(self):
        with patch.object(vision.Path,'is_file',return_value=False):
            with self.assertRaisesRegex(RuntimeError,'缺失'):
                vision.configure_ocr(strict=True)

    def card_image(self,color):
        image=np.full((100,100,3),255,np.uint8)
        image[30:39,36:45]=color
        return image

    def test_dark_hex_accepts_quantized_linear_swatch(self):
        # Captured #080803 is displayed as approximately #0D0D00.
        with patch('vision._tesseract',return_value='#080803') as ocr:
            result=vision.read_codes(self.card_image((13,13,0)),[(0,0,80,80)],[(40,90)])
        self.assertEqual(result,['#080803']);self.assertEqual(ocr.call_count,1)

    def test_low_digit_misread_does_not_stop_before_better_ocr(self):
        with patch('vision._tesseract',side_effect=['#714124','#71412A']) as ocr:
            result=vision.read_codes(self.card_image((113,64,42)),[(0,0,80,80)],[(40,90)])
        self.assertEqual(result,['#71412A']);self.assertEqual(ocr.call_count,2)

    def test_plausible_wrong_hex_is_rejected_without_guessing(self):
        for text,swatch in [('#714124',(113,64,42)),('#0C1E1F',(0,22,29))]:
            with self.subTest(text=text),patch('vision._tesseract',return_value=text):
                result=vision.read_codes(self.card_image(swatch),[(0,0,80,80)],[(40,90)])
            self.assertEqual(result,[None])

    def test_direct_swatch_is_still_supported(self):
        with patch('vision._tesseract',return_value='#080803'):
            result=vision.read_codes(self.card_image((8,8,3)),[(0,0,80,80)],[(40,90)])
        self.assertEqual(result,['#080803'])

    def test_archived_heldout_hex_including_four_previous_misses(self):
        root=Path(__file__).resolve().parents[2]
        source=root/'outputs/atlas-capture-20260927-010944-159'
        manifest=root/'outputs/search-review-20260927-010944-stable/verified-heldout-codes.json'
        if not manifest.is_file() or not source.is_dir():self.skipTest('Local capture archive unavailable')
        if not vision.configure_ocr():self.skipTest('Tesseract unavailable')
        scene=next(r for r in json.loads((source/'log.json').read_text()) if r.get('kind')=='sampling_ready')
        for row in json.loads(manifest.read_text())['rows']:
            with self.subTest(frame=row['frame']):
                image=np.array(Image.open(source/(row['frame']+'.png')).convert('RGB'))
                codes=vision.read_codes(image,scene['cards'],scene['markers'])
                self.assertEqual(codes,[r['verified_game_hex'] for r in row['checks']])


if __name__=='__main__':unittest.main()
