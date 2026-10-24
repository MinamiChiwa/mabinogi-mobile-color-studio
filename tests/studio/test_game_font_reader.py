"""Real text pixels must improve without a native or target-color hint."""
import time, unittest
from pathlib import Path
from unittest.mock import patch
import cv2, numpy as np
from PIL import Image
from native_live.dye_hex_glyphs import read_card_glyphs
from native_live.probe_timer import read_timer

FIXTURES=Path(__file__).resolve().parents[2]/'fixtures'

class GameFontReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from native_live.game_font_reader import prepare_game_font_assets
        prepare_game_font_assets()

    def test_real_low_nibble_a_reads_without_slow_ocr(self):
        image=np.array(Image.open(FIXTURES/'native-hex-conflict/cards.png').convert('RGB'))
        result=read_card_glyphs(image,(346,10,79,79),deadline=time.monotonic()+1.)
        self.assertEqual(result['hex'],'#72514A')
        self.assertTrue(result['glyphs_unambiguous'])

    def test_countdown_real_digits_need_no_ocr_subprocess(self):
        image=np.array(Image.open(FIXTURES/'screenshot-feedback/timer-39.png').convert('RGB'))
        with patch('native_live.probe_timer.ocr',side_effect=AssertionError('Font digits should avoid OCR')):
            result=read_timer(image,deadline=time.monotonic()+1.)
        self.assertEqual(result['remaining_seconds'],39)
        self.assertEqual(result['timer_confidence'],'two_pass_agree')

    def test_screenshot_strategy_also_uses_font_text_for_hex_and_countdown(self):
        from screenshot_text import read_visible,read_timer as screenshot_timer
        image=np.array(Image.open(FIXTURES/'native-hex-conflict/cards.png').convert('RGB'))
        cards=[(17,10,80,80),(181,10,80,80),(346,10,79,79)]
        with patch('screenshot_text._tesseract',side_effect=AssertionError('Certified font text needs no OCR')):
            values,_=read_visible(image,cards,deadline=time.monotonic()+1.)
            timer_image=np.array(Image.open(FIXTURES/'screenshot-feedback/final-19.png').convert('RGB'))
            seconds=screenshot_timer(timer_image,113,deadline=time.monotonic()+1.)
        self.assertEqual(values,['#F27233','#EAD310','#72514A'])
        self.assertEqual(seconds,19)

    def test_blank_card_never_generates_color_digits(self):
        result=read_card_glyphs(np.full((100,100,3),255,np.uint8),(0,0,100,100),deadline=time.monotonic()+1.)
        self.assertIsNone(result['hex'])

    def test_three_digit_leading_one_is_not_dropped_and_single_digit_is_supported(self):
        for want in (105,117,9):
            with self.subTest(seconds=want):
                image=np.array(Image.open(FIXTURES/'game-font'/f'timer-{want}.png').convert('RGB'))
                with patch('native_live.probe_timer.ocr',side_effect=AssertionError('Complete font digits need no OCR')):
                    result=read_timer(image,deadline=time.monotonic()+1.)
                self.assertEqual(result['remaining_seconds'],want)
                self.assertEqual(len(result['timer_localization']['digit_components']),len(str(want)))

    def test_countdown_outlier_is_rejected_without_manufacturing_previous_digits(self):
        image=np.array(Image.open(FIXTURES/'game-font/timer-117.png').convert('RGB'))
        result=read_timer(image,deadline=time.monotonic()+1.,previous=(35,10.),captured_at=11.)
        self.assertIsNone(result['remaining_seconds'])
        self.assertEqual(result['timer_font_read']['text'],'117')

    def test_dimmer_leading_one_is_not_cropped_before_text_read(self):
        from native_live.probe_timer import locate_timer
        image=np.array(Image.open(FIXTURES/'game-font/timer-115.png').convert('RGB'))
        located=locate_timer(image)
        x,y,w,h=located['digit_components'][0]
        digit=image[y:y+h,x:x+w]
        digit[np.all(digit>=170,axis=2)]=205
        with patch('native_live.probe_timer.ocr',side_effect=AssertionError('Visible leading digit must survive localization')):
            result=read_timer(image,deadline=time.monotonic()+1.)
        self.assertEqual(result['remaining_seconds'],115)
        self.assertEqual(len(result['timer_localization']['digit_components']),3)

    def test_single_digit_centered_caption_survives_window_scaling(self):
        original=np.array(Image.open(FIXTURES/'game-font/timer-9.png').convert('RGB'))
        for scale in (.75,1.25,1.5,2.):
            with self.subTest(scale=scale):
                image=cv2.resize(original,None,fx=scale,fy=scale,interpolation=cv2.INTER_LINEAR)
                result=read_timer(image,deadline=time.monotonic()+1.)
                self.assertEqual(result['remaining_seconds'],9)

    def test_missing_hex_character_cannot_be_replaced_by_a_color_or_template(self):
        image=np.array(Image.open(FIXTURES/'native-hex-conflict/cards.png').convert('RGB'))
        image[71:85,383:392]=255
        result=read_card_glyphs(image,(346,10,79,79),deadline=time.monotonic()+1.)
        self.assertIsNone(result['hex'])

    def test_stop_midway_through_character_read_propagates(self):
        image=np.array(Image.open(FIXTURES/'native-hex-conflict/cards.png').convert('RGB'))
        calls=0
        def stop():
            nonlocal calls
            calls+=1
            if calls==4:raise InterruptedError('F9 during text read')
        with self.assertRaises(InterruptedError):
            read_card_glyphs(image,(346,10,79,79),deadline=time.monotonic()+1.,check=stop)

    def test_real_cancel_and_deadline_remain_effective(self):
        image=np.full((100,100,3),255,np.uint8)
        def stop():raise InterruptedError('F9')
        with self.assertRaises(InterruptedError):read_card_glyphs(image,(0,0,100,100),deadline=time.monotonic()+1.,check=stop)
        with self.assertRaises(TimeoutError):read_card_glyphs(image,(0,0,100,100),deadline=time.monotonic()-1.)

if __name__=='__main__':unittest.main()
