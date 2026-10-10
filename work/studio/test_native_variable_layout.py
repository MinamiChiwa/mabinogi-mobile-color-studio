"""Physical layout regression; synthetic pixel fixtures never send game input."""
import inspect
import math
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np
from native_live import project_probe_io as io


def palette_frame(extent=(1280,960),scale=1.,origin=(700,420)):
    """Draw cards/stems/rings at a measured board, independently of client size."""
    w,h=extent;l,t=origin;side=round(500*scale)
    image=np.full((h,w,3),60,np.uint8)
    board=[l,t,l+side,t+side]
    image[t:t+side,l:l+side]=(40,50,60)
    colors=['#112233','#445566','#778899'];centers=[];markers=[]
    for index,color in enumerate(colors):
        cx=round(l+(index+.5)*side/3);cw=round(81*scale);cy=round(t-105*scale)
        x=cx-cw//2;card=(x,cy,cw,cw)
        image[cy:cy+cw,x:x+cw]=255
        sample=tuple(int(color[i:i+2],16) for i in (1,3,5))
        image[cy+round(cw*.17):cy+round(cw*.68),x+round(cw*.17):x+round(cw*.83)]=sample
        my=round(t+(120,260,350)[index]*scale)
        cv2.line(image,(cx,cy+cw),(cx,my), (255,255,255),max(1,round(2*scale)))
        cv2.circle(image,(cx,my),max(3,round(8*scale)),(255,255,255),-1)
        cv2.circle(image,(cx,my),max(1,round(5*scale)),sample,-1)
        centers.append(cx);markers.append((cx,my))
    return image,board,colors,centers,markers


class NativeVariableLayoutTests(unittest.TestCase):
    def read(self,image,board,**kwargs):
        options=dict(deadline=100.,clock=lambda:1.,timer_mode='skip')
        # Before implementation, fail on the physical behavior instead of a
        # TypeError for the absent optional native geometry interface.
        if 'native_board' in inspect.signature(io.read_probe_frame).parameters:
            options['native_board']=board
        options.update(kwargs)
        with patch.object(io,'read_codes',return_value=[None]*3):
            return io.read_probe_frame(image,**options)

    def test_positive_client_extents_do_not_require_four_by_three(self):
        for extent in ((800,600),(960,720),(1280,960),(1600,1200),(1920,1080),
                       (2560,1440),(3840,2160),(900,1600),(320,240),(16000,9000)):
            with self.subTest(extent=extent):
                try:scale=io.probe_layout_scale(*extent)
                except ValueError as exc:self.fail('Valid physical extent rejected: '+str(exc))
                self.assertTrue(math.isfinite(scale) and scale>0)

    def test_malformed_physical_extents_are_rejected(self):
        for extent in ((0,960),(-1280,960),(True,960),(1280.,960),(1280,False),
                       (1280,math.nan),(16385,960),(1280,16385)):
            with self.subTest(extent=extent),self.assertRaises(ValueError):io.probe_layout_scale(*extent)

    def test_cards_and_markers_follow_native_board_at_variable_client_extents(self):
        cases=[((960,720),.75,(530,310)),((1280,960),1.,(700,420)),
               ((1600,1200),1.25,(900,525)),((1920,1080),1.,(1350,500)),
               ((2560,1440),1.,(1900,800)),((3840,2160),1.,(3250,1500)),
               ((3840,2160),2.,(2500,1000)),((3840,2160),3.,(2200,500)),
               ((800,600),.55,(490,270)),((900,1600),1.,(200,1000))]
        for extent,scale,origin in cases:
            with self.subTest(extent=extent,scale=scale,origin=origin):
                image,board,colors,centers,markers=palette_frame(extent,scale,origin)
                try:observed=self.read(image,board)
                except ValueError as exc:self.fail('Measured visible layout rejected: '+str(exc))
                self.assertEqual(len(observed['cards']),3)
                for card,cx,marker,want_marker in zip(observed['cards'],centers,observed['markers'],markers):
                    self.assertAlmostEqual(card[0]+card[2]/2,cx,delta=max(2,scale))
                    self.assertAlmostEqual(marker[0],want_marker[0],delta=max(2,scale))
                    self.assertAlmostEqual(marker[1],want_marker[1],delta=max(2,scale))
                self.assertEqual(observed['hex'],[None]*3,'Geometry must not fabricate screenshot HEX')

    def test_small_ui_in_four_k_client_ignores_unrelated_card_triple(self):
        image,board,_,centers,_=palette_frame((3840,2160),1.,(3200,1500))
        decoy,_,_,_,_=palette_frame((1280,960),1.,(100,300))
        image[:960,:1280]=decoy
        try:observed=self.read(image,board)
        except ValueError as exc:self.fail('Native anchored card search failed: '+str(exc))
        for card,cx in zip(observed['cards'],centers):
            self.assertAlmostEqual(card[0]+card[2]/2,cx,delta=1.)

    def test_wrong_native_board_cannot_authorize_a_visible_other_palette(self):
        image,_,_,_,_=palette_frame((3840,2160),1.,(3200,1500))
        with self.assertRaises(ValueError):self.read(image,[100,500,600,1000])

    def test_blank_frame_cannot_be_filled_from_native_geometry(self):
        with self.assertRaises(ValueError):self.read(np.zeros((2160,3840,3),np.uint8),[3200,1500,3700,2000])

    def test_native_board_must_be_finite_square_and_inside_frame(self):
        image,board,_,_,_=palette_frame()
        for bad in ([0,0,0,0],[700,420,1200,850],[-1,420,500,920],
                    [700,420,1300,1020],[700,420,math.nan,920],['700',420,1200,920]):
            with self.subTest(board=bad),self.assertRaises(ValueError):self.read(image,bad)

    def test_native_hint_never_overrides_screenshot_native_hex_disagreement(self):
        image,board,_,_,_=palette_frame((1920,1080),1.,(1350,500))
        result=self.read(image,board)
        result['hex']=['#112233',None,None]
        with self.assertRaisesRegex(ValueError,'Screenshot and checkpoint HEX disagree'):
            io.merge_native_hex(result,['#FFFFFF','#445566','#778899'])

    def test_native_layout_read_observes_cancel_before_recognition(self):
        image,board,_,_,_=palette_frame((3840,2160),1.,(3200,1500))
        def cancelled():raise InterruptedError('F9')
        with self.assertRaises(InterruptedError):self.read(image,board,check=cancelled)

    def test_expired_deadline_is_not_hidden_by_wide_client(self):
        image,board,_,_,_=palette_frame((3840,2160),1.,(3200,1500))
        with self.assertRaises(TimeoutError):self.read(image,board,deadline=0.)

    def test_project_io_passes_checkpoint_geometry_and_retains_fresh_physical_frames(self):
        image,board,codes,_,_=palette_frame((3840,2160),1.,(3200,1500))
        observation=dict(session_token=['session'],process_identity=[1,2,3,'build'],
            motion=dict(binding={},settings={}),window_context=dict(window=dict(client_size_physical=[3840,2160])),
            window_mapping_candidate=dict(client_board_candidate=board))
        game=SimpleNamespace(check=lambda:None,capture=lambda:image.copy())
        with tempfile.TemporaryDirectory() as folder:
            adapter=io.ProjectProbeIO(None,dict(session_deadline_monotonic=float('inf'),baseline=observation),
                folder,game=game,f9_pressed=lambda:False)
            adapter.check=lambda deadline:None;adapter._input_guard=lambda:None
            adapter.last_client_hex=codes;adapter.timer_grace_until=float('inf')
            with patch.object(io,'read_codes',return_value=[None]*3):
                try:frames=adapter.frames('layout',float('inf'))
                except ValueError as exc:self.fail('Physical frame/native geometry integration failed: '+str(exc))
            self.assertEqual(len(frames),2)
            self.assertTrue(all(f['hex']==codes for f in frames))
            self.assertTrue(all(f['hex_source']==['native_checkpoint']*3 for f in frames))
            self.assertTrue(all(f['screenshot_hex_verified'] is False for f in frames))

    def test_capture_extent_mismatch_is_rejected_before_layout_read(self):
        image,board,_,_,_=palette_frame()
        observation=dict(session_token=['session'],process_identity=[1,2,3,'build'],motion=dict(binding={},settings={}),
            window_context=dict(window=dict(client_size_physical=[3840,2160])),
            window_mapping_candidate=dict(client_board_candidate=board))
        game=SimpleNamespace(check=lambda:None,capture=lambda:image)
        with tempfile.TemporaryDirectory() as folder:
            adapter=io.ProjectProbeIO(None,dict(session_deadline_monotonic=float('inf'),baseline=observation),
                folder,game=game,f9_pressed=lambda:False)
            adapter.check=lambda deadline:None;adapter._input_guard=lambda:None
            with self.assertRaisesRegex(ValueError,'physical client extent mismatch'):adapter.frames('layout',float('inf'))


if __name__=='__main__':unittest.main()
