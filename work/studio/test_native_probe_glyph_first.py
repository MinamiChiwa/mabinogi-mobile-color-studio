"""Trusted screenshot glyphs avoid OCR; rejected glyphs retain OCR validation."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import cv2
import numpy as np
from native_live import project_probe_io as io
from native_live.dye_hex_glyphs import _load, read_card_glyphs


class GlyphFirstFrameTests(unittest.TestCase):
    def boundary_frame(self):
        asset = _load(); labels = asset['labels_160']; patterns = asset['patterns_160']
        reference = np.full((81, 81, 3), 255, np.uint8)
        code = '#F9F6F6'
        for position, char in enumerate(code):
            glyph = patterns[np.where(labels == char)[0][0]] > .5
            glyph = cv2.resize(glyph.astype(np.uint8), (8, 12), interpolation=cv2.INTER_NEAREST)
            x = 7 + position * 9
            reference[62:74, x:x + 8][glyph.astype(bool)] = 0
        image = np.full((960, 1280, 3), 255, np.uint8)
        image[100:200, 100:200] = cv2.resize(reference, (100, 100), interpolation=cv2.INTER_CUBIC)
        image[135:153, 140:160] = (250, 244, 244)
        scene = SimpleNamespace(cards=[[100, 100, 100, 100]], markers=[(150, 300)], board=[0, 200, 600, 800])
        return image, scene, code

    def test_two_threshold_text_at_swatch_boundary_remains_screenshot_evidence(self):
        image, scene, code = self.boundary_frame()
        cache = {}
        with patch.object(io, 'recognize', return_value=scene), \
             patch('vision._tesseract', side_effect=AssertionError('Certified glyph text needs no OCR')):
            first = io.read_probe_frame(image, deadline=100., clock=lambda:1.,
                hex_fallback=read_card_glyphs, timer_mode='skip', card_cache=cache)
            second = io.read_probe_frame(image.copy(), deadline=100., clock=lambda:1.,
                hex_fallback=read_card_glyphs, timer_mode='skip', card_cache=cache)
        self.assertEqual(first['hex'], [code])
        self.assertTrue(first['hex_fallback_reads'][0]['swatch_accepted'])
        self.assertEqual(second['hex_cache_hits'], [True])

    def test_text_outside_swatch_boundary_stays_unknown(self):
        image, scene, code = self.boundary_frame()
        image[135:153, 140:160] = (251, 244, 244)
        with patch.object(io, 'recognize', return_value=scene), \
             patch('vision._tesseract', return_value=''), patch('vision.ocr', return_value=''):
            result = io.read_probe_frame(image, deadline=100., clock=lambda:1.,
                hex_fallback=read_card_glyphs, timer_mode='skip')
        self.assertEqual(result['hex'], [None])
        self.assertFalse(result['hex_fallback_reads'][0]['swatch_accepted'])

    def test_ordinary_ocr_keeps_strict_swatch_boundary(self):
        import vision
        image, scene, code = self.boundary_frame()
        with patch('vision._tesseract', return_value=code), patch('vision.ocr', return_value=code):
            result = vision.read_codes(image, scene.cards, scene.markers, deadline=100., clock=lambda:1.)
        self.assertEqual(result, [None])

    def frame(self):
        image=np.full((960,1280,3),255,dtype=np.uint8)
        cards=[[100,100,80,80],[300,100,80,80],[500,100,80,80]]
        for card,color in zip(cards,[(17,34,51),(68,85,102),(119,136,153)]):
            x,y,w,h=card;image[y:y+60,x:x+w]=color
        return image,SimpleNamespace(cards=cards,markers=[(140,300),(340,300),(540,300)],board=[0,200,600,800])

    def read(self,image,scene,glyphs,ocr):
        def text_reader(image,card,**unused):
            return glyphs[scene.cards.index(list(card))]
        with patch.object(io,'recognize',return_value=scene),patch('vision._tesseract',side_effect=ocr):
            return io.read_probe_frame(image,deadline=100.,clock=lambda:1.,hex_fallback=text_reader,timer_mode='skip')

    def trusted_glyphs(self):
        return [dict(hex=code,glyphs_unambiguous=True,method='two_threshold_reference_glyphs')
                for code in ['#112233','#445566','#778899']]

    def test_unambiguous_glyphs_matching_swatches_return_hex_without_ocr(self):
        image,scene=self.frame()
        def unexpected_ocr(*args,**kwargs):
            self.fail('Trusted glyphs invoked the slow OCR subprocess')
        result=self.read(image,scene,self.trusted_glyphs(),unexpected_ocr)
        self.assertEqual(result['hex'],['#112233','#445566','#778899'])
        self.assertEqual([r['swatch_accepted'] for r in result['hex_fallback_reads']],[True,True,True])

    def test_only_uncertain_or_disagreeing_card_uses_original_ocr(self):
        for rejected in [dict(hex=None,glyphs_unambiguous=False),
                         dict(hex='#010203',glyphs_unambiguous=True),
                         dict(hex='#XYZXYZ',glyphs_unambiguous=True)]:
            with self.subTest(rejected=rejected):
                image,scene=self.frame();glyphs=self.trusted_glyphs();glyphs[1]=rejected
                calls=[]
                def ocr(crop,**unused):
                    calls.append(crop)
                    return '#445566'
                result=self.read(image,scene,glyphs,ocr)
                self.assertEqual(result['hex'],['#112233','#445566','#778899'])
                self.assertEqual(len(calls),1,'Only the unresolved card needs OCR')
                self.assertFalse(result['hex_fallback_reads'][1]['swatch_accepted'])


if __name__=='__main__':unittest.main()
