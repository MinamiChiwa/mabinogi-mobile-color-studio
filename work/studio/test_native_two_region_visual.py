"""Two physical regions use real screenshot glyphs and never invent a third."""
import inspect
import tempfile
import unittest
from pathlib import Path
import threading
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np

import vision
from native_live import project_probe_io as probe
from native_live.dye_hex_glyphs import _load, read_card_glyphs


def dye_frame(count=2, missing=None, board_visible=True):
    image=np.full((1300,1600,3),24,np.uint8)
    board=(200,288,1100,1188)
    if board_visible:
        image[288:1188,200:1100]=(50,80,90)
        cv2.rectangle(image,(200,288),(1099,1187),(195,195,195),2)
    asset=_load();labels=asset['labels_160'];patterns=asset['patterns_160']
    codes=['#112233','#445566','#778899'][:count]
    for index,code in enumerate(codes):
        if index==missing:continue
        center=int(200+(index+.5)*900/count);x=center-75;y=100
        image[y:y+150,x:x+150]=255
        image[y+38:y+85,x+20:x+130]=vision.rgb(code)
        for position,char in enumerate(code):
            glyph=patterns[np.where(labels==char)[0][0]]>.5
            image[y+114:y+138,x+15+position*18:x+31+position*18][glyph]=0
        cv2.line(image,(center,250),(center,455),(255,255,255),3)
        cv2.circle(image,(center,470),15,(255,255,255),2)
    return image,board,codes


class NativeTwoRegionVisualTests(unittest.TestCase):
    def test_visible_translation_uses_both_actual_material_halves(self):
        image=np.full((300,300,3),80,np.uint8)
        image[180:185,74:79]=(255,0,0);image[180:185,224:229]=(0,255,0)
        scene=vision.Scene([],[(75,150),(225,150)],(0,0,300,300),[None,None],120,None)
        rules=[dict(enabled=True,colors=['#FF0000'],exact=True,tolerance=0.),
               dict(enabled=True,colors=['#00FF00'],exact=True,tolerance=0.)]
        move=vision.candidate_shift(image,scene,rules)
        self.assertIsNotNone(move)
        self.assertLessEqual(abs(move[0]+1),2);self.assertLessEqual(abs(move[1]+32),2)
        self.assertEqual(move[2],0.)
        with self.assertRaises(ValueError):vision.candidate_shift(image,scene,[*rules,rules[0]])

    def test_visual_acquisition_rejects_only_absent_third_before_any_input(self):
        from live_atlas_capture import acquire
        image,board,_=dye_frame();commands=[];events=[]
        game=SimpleNamespace(initial=(0,0,1600,1300),until=float('inf'),stage_until=float('inf'),
            geometry=lambda:(0,0,1600,1300),capture=lambda:image,capture_waiting=lambda:image,
            check=lambda:None,pause=lambda seconds:None)
        def forbidden(kind):
            def input_call(*args,**kwargs):
                commands.append(kind);raise ValueError('Input must not precede region binding')
            return input_call
        for kind in ('wheel','drag','rotate','move_to','click','send'):
            setattr(game,kind,forbidden(kind))
        rules=[dict(enabled=False,colors=[],exact=True,tolerance=0.),
               dict(enabled=False,colors=[],exact=True,tolerance=0.),
               dict(enabled=True,colors=['#112233'],exact=True,tolerance=0.)]
        def layout(frame,**unused):
            scene=vision.recognize(frame,with_ocr=False);scene.seconds=120
            return scene
        with tempfile.TemporaryDirectory() as folder, \
             patch('live_atlas_capture.CaptureGame',return_value=game), \
             patch('live_atlas_capture.configure_ocr'), \
             patch('live_atlas_capture.recognize',side_effect=layout):
            options=dict(strategy='grid',stop=threading.Event(),emit=lambda kind,**data:events.append((kind,data)))
            if 'rules' in inspect.signature(acquire).parameters:options['rules']=rules
            with self.assertRaises(ValueError):acquire(Path(folder)/'capture',**options)
        self.assertEqual(commands,[],'An unavailable target cannot justify acquisition input')
        self.assertTrue(rules[2]['enabled'])
        bound=next(data for kind,data in events if kind=='region_layout')
        self.assertEqual(bound['region_count'],2)
        self.assertEqual(len(bound['rules']),2)

    def native_frame(self,image,board,count):
        kwargs=dict(deadline=100.,clock=lambda:1.,native_board=board,
                    hex_fallback=read_card_glyphs,timer_mode='skip')
        if 'region_count' in inspect.signature(probe.read_probe_frame).parameters:
            kwargs['region_count']=count
        return probe.read_probe_frame(image,**kwargs)

    def test_two_cards_decode_both_actual_glyphs_and_match_checkpoint(self):
        image,board,codes=dye_frame()
        frame=self.native_frame(image,board,2)
        self.assertEqual(frame['hex'],['#112233','#445566'])
        self.assertEqual(len(frame['cards']),2)
        self.assertEqual(len(frame['markers']),2)
        merged=probe.merge_native_hex(frame,codes)
        self.assertEqual(merged['hex_source'],['screenshot','screenshot'])
        self.assertTrue(merged['screenshot_hex_verified'])
        with self.assertRaises(ValueError):probe.merge_native_hex(frame,[*codes,'#778899'])

    def test_three_region_binding_with_one_hidden_card_is_rejected(self):
        for missing in range(3):
            with self.subTest(missing=missing):
                image,board,_=dye_frame(3,missing=missing)
                with self.assertRaises(ValueError):self.native_frame(image,board,3)

    def test_two_region_binding_rejects_visible_three_region_layout(self):
        image,board,_=dye_frame(3)
        with self.assertRaises(ValueError):self.native_frame(image,board,2)

    def test_two_region_binding_does_not_accept_occluded_three_region_layout(self):
        for missing in range(3):
            with self.subTest(missing=missing):
                image,board,_=dye_frame(3,missing=missing)
                with self.assertRaises(ValueError):self.native_frame(image,board,2)

    def test_frames_use_bound_count_and_preserve_two_screenshot_reads(self):
        image,board,codes=dye_frame()
        observation=dict(session_token=[0,0,'result',[],0,[[0,'pixels0','y0'],[1,'pixels1','y1']],'ratio'],process_identity=[1,2,3,'build'],
            motion=dict(binding={},settings={}),window_context=dict(window=dict(client_size_physical=[1600,1300])),
            window_mapping_candidate=dict(client_board_candidate=board))
        for explicit_count in (False,True):
            with self.subTest(explicit_count=explicit_count),tempfile.TemporaryDirectory() as folder:
                if explicit_count:observation['region_count']=2
                io=probe.ProjectProbeIO(None,dict(session_deadline_monotonic=float('inf'),baseline=observation),
                    folder,game=SimpleNamespace(check=lambda:None,capture=lambda:image),f9_pressed=lambda:False)
                io.check=lambda deadline:None;io._input_guard=lambda:None
                io.last_client_hex=codes;io.hex_fallback=read_card_glyphs;io.timer_grace_until=float('inf')
                frames=io.frames('initial',float('inf'))
                self.assertEqual([frame['hex'] for frame in frames],[codes,codes])
                self.assertEqual(frames[1]['hex_cache_hits'],[True,True])

    def test_legacy_automatic_two_regions_require_complete_board_boundary(self):
        image,board,_=dye_frame()
        scene=vision.recognize(image,with_ocr=False)
        self.assertEqual(len(scene.cards),2)
        self.assertEqual(scene.board,board)
        image,_,_=dye_frame(board_visible=False)
        with self.assertRaises(ValueError):vision.recognize(image,with_ocr=False)

    def test_legacy_three_regions_with_hidden_card_do_not_become_two(self):
        for missing in range(3):
            with self.subTest(missing=missing):
                image,_,_=dye_frame(3,missing=missing)
                with self.assertRaises(ValueError):vision.recognize(image,with_ocr=False)


if __name__=='__main__':unittest.main()
