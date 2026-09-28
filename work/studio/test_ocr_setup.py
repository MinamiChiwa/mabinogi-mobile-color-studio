import unittest
from unittest.mock import patch
import numpy as np
import vision
import json
from pathlib import Path
from PIL import Image
from subprocess import CompletedProcess,TimeoutExpired


class OcrSetupTests(unittest.TestCase):
    def setUp(self):
        self.old_state=vision.OCR_AVAILABLE
        self.addCleanup(setattr,vision,'OCR_CONFIG',vision.OCR_CONFIG)
        vision.OCR_CONFIG=''
        self.old_command=vision.pytesseract.pytesseract.tesseract_cmd
        self.addCleanup(setattr,vision,'OCR_AVAILABLE',self.old_state)
        self.addCleanup(setattr,vision.pytesseract.pytesseract,'tesseract_cmd',self.old_command)

    def test_project_local_ocr_is_found_after_moving_checkout(self):
        expected=vision.Path(vision.__file__).resolve().parents[2]/'outputs/dependencies/ocr/tesseract.exe'
        with patch.object(vision.Path,'is_file',autospec=True,side_effect=lambda p:p==expected), \
             patch('vision.subprocess.run',return_value=CompletedProcess([],0,b'Languages:\neng\n')):
            self.assertTrue(vision.configure_ocr(strict=True))
        self.assertEqual(vision.pytesseract.pytesseract.tesseract_cmd,str(expected))
        self.assertTrue(vision.OCR_AVAILABLE)

    def test_missing_english_data_blocks_formal_capture(self):
        with patch.object(vision.Path,'is_file',return_value=True), \
             patch('vision.subprocess.run',return_value=CompletedProcess([],0,b'Languages:\nosd\n')):
            with self.assertRaisesRegex(RuntimeError,'文字识别'):
                vision.configure_ocr(strict=True)
        self.assertFalse(vision.OCR_AVAILABLE)

    def test_missing_executable_blocks_formal_capture(self):
        with patch.object(vision.Path,'is_file',return_value=False):
            with self.assertRaisesRegex(RuntimeError,'缺失'):
                vision.configure_ocr(strict=True)

    def test_failed_first_install_falls_back_to_next_ocr_executable_without_caching(self):
        with patch.object(vision.Path,'is_file',return_value=True), \
             patch('vision.shutil.which',return_value=None), \
             patch('vision.subprocess.run',side_effect=[CompletedProcess([],1,b'error'),CompletedProcess([],0,b'eng\n')]) as probe:
            self.assertTrue(vision.configure_ocr(strict=True))
        self.assertEqual(probe.call_count,2)
        self.assertNotEqual(probe.call_args_list[0].args[0][0],probe.call_args_list[1].args[0][0])
        self.assertTrue(vision.OCR_AVAILABLE)

    def test_non_utf8_path_in_language_list_does_not_reject_working_ocr(self):
        for encoding in ('cp936','cp950','cp1252'):
            with self.subTest(encoding=encoding):
                header=('C:/使用者/染色工具' if encoding!='cp1252' else 'C:/Utilisateurs/café').encode(encoding)
                with patch.object(vision.Path,'is_file',return_value=True), \
                     patch('vision.subprocess.run',return_value=CompletedProcess([],0,b'Languages in "'+header+b'":\r\neng\r\n')):
                    self.assertTrue(vision.configure_ocr(strict=True))

    def test_hung_ocr_probe_falls_back_and_each_probe_has_a_timeout(self):
        with patch.object(vision.Path,'is_file',return_value=True), \
             patch('vision.subprocess.run',side_effect=[TimeoutExpired('tesseract',5),CompletedProcess([],0,b'eng\n')]) as probe:
            self.assertTrue(vision.configure_ocr(strict=True))
        self.assertTrue(all(call.kwargs['timeout']==5 for call in probe.call_args_list))

    def test_bundled_data_directory_is_used_by_probe_and_runtime(self):
        with patch.object(vision.Path,'is_file',return_value=True), \
             patch('vision.subprocess.run',return_value=CompletedProcess([],0,b'eng\n')) as probe:
            self.assertTrue(vision.configure_ocr(strict=True))
        args=probe.call_args.args[0]
        self.assertEqual(args[2],'--tessdata-dir')
        self.assertEqual(vision.OCR_CONFIG,f'--tessdata-dir "{args[3]}"')
        with patch('vision._ocr_text',return_value='#ABCDEF') as read:
            vision._tesseract('image','--psm 7')
        self.assertEqual(read.call_args.kwargs['config'],vision.OCR_CONFIG+' --psm 7')

    def card_image(self,color):
        image=np.full((100,100,3),255,np.uint8)
        image[30:39,36:45]=color
        return image

    def test_ocr_language_is_independent_of_ui_and_system_language(self):
        vision.OCR_AVAILABLE=True
        with patch('vision._ocr_text',return_value=' #ABCDEF ') as read:
            self.assertEqual(vision._tesseract('image','--psm 7',timeout=1.5),'#ABCDEF')
        read.assert_called_once_with('image',lang='eng',config='--psm 7',timeout=1.5)

    def test_transient_ocr_errors_do_not_disable_later_frames(self):
        for failure in (RuntimeError('Tesseract process timeout'),TimeoutExpired('tesseract',2),
                        vision.pytesseract.TesseractError(1,'temporary frame failure'),
                        UnicodeDecodeError('utf-8',b'\xff',0,1,'localized output')):
            with self.subTest(failure=type(failure).__name__):
                vision.OCR_AVAILABLE=True
                with patch('vision._ocr_text',side_effect=[failure,'#AABBCC']):
                    self.assertEqual(vision._tesseract('image',''),'')
                    self.assertTrue(vision.OCR_AVAILABLE)
                    self.assertEqual(vision._tesseract('next frame',''),'#AABBCC')

    def test_unexpected_ocr_runtime_error_is_not_silently_swallowed(self):
        vision.OCR_AVAILABLE=True
        with patch('vision._ocr_text',side_effect=RuntimeError('unexpected bug')):
            with self.assertRaisesRegex(RuntimeError,'unexpected bug'):
                vision._tesseract('image','')

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
