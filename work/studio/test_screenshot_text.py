import time,unittest
from pathlib import Path
from PIL import Image
import numpy as np
import cv2
from screenshot_text import read_visible,read_timer
from vision import configure_ocr

class ScreenshotTextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):configure_ocr(strict=True)

    def test_recorded_missed_text_reads_all_three_without_swatches_supplying_digits(self):
        image=np.array(Image.open(Path(__file__).with_name('screenshot_text_fixture.png')).convert('RGB'))
        values,diagnostics=read_visible(image,[(11,12,113,113),(245,12,113,113),(478,12,113,113)],
            deadline=time.monotonic()+4)
        self.assertEqual(values,['#FDEAEF','#F1F1F1','#EEEBE8'])
        self.assertTrue(all(len(row['reads'])>=2 for row in diagnostics))

    def test_blank_white_swatches_do_not_claim_matching_hex(self):
        values,_=read_visible(np.full((100,220,3),255,np.uint8),[(0,0,100,100),(110,0,100,100)],
            deadline=time.monotonic()+4)
        self.assertEqual(values,[None,None])

    def test_recorded_short_bar_timers_keep_complete_digit_shapes(self):
        folder=Path(__file__).resolve().parents[2]/'fixtures/screenshot-feedback'
        for name,want in [('timer-39.png',39),('timer-30.png',30),('final-19.png',19)]:
            with self.subTest(frame=name):
                image=np.array(Image.open(folder/name).convert('RGB'))
                self.assertEqual(read_timer(image,113),want)

    def test_recorded_final_hex_does_not_lose_zero(self):
        path=Path(__file__).resolve().parents[2]/'fixtures/screenshot-feedback/final-19.png'
        image=np.array(Image.open(path).convert('RGB'))
        values,diagnostics=read_visible(image,[(1186,117,113,113),(1420,117,113,113),(1653,117,113,113)],
            deadline=time.monotonic()+4)
        self.assertEqual(values,['#FFFFFF','#CBCBCB','#B9E0F0'])
        self.assertGreaterEqual(sum(row['hex']=='#B9E0F0' for row in diagnostics[2]['reads']),2)

    def test_recorded_zero_is_read_across_resized_card_pixels(self):
        path=Path(__file__).resolve().parents[2]/'fixtures/screenshot-feedback/final-19.png'
        original=np.array(Image.open(path).convert('RGB'))
        cards=[(1186,117,113,113),(1420,117,113,113),(1653,117,113,113)]
        for scale in (.5,.75,1.25,1.5,2):
            with self.subTest(scale=scale):
                image=cv2.resize(original,None,fx=scale,fy=scale,interpolation=cv2.INTER_LINEAR)
                boxes=[tuple(round(v*scale) for v in card) for card in cards]
                values,_=read_visible(image,boxes,deadline=time.monotonic()+4)
                self.assertEqual(values,['#FFFFFF','#CBCBCB','#B9E0F0'])

    def test_missing_character_is_not_filled_from_swatch(self):
        from unittest.mock import patch
        image=np.full((100,100,3),255,np.uint8)
        for text in ('#FFFFF','#FFFFFFF'):
            with self.subTest(text=text),patch('screenshot_text._tesseract',return_value=text):
                values,_=read_visible(image,[(0,0,100,100)],deadline=time.monotonic()+4)
                self.assertEqual(values,[None])

if __name__=='__main__':unittest.main()
