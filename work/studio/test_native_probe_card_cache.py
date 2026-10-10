"""Exact screenshot-card reuse keeps fresh frames and native color checks."""
import inspect
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from native_live import project_probe_io as io


class ProbeCardCacheTests(unittest.TestCase):
    def setUp(self):
        self.image=np.full((960,1280,3),255,dtype=np.uint8)
        self.cards=[[100,100,80,80],[300,100,80,80],[500,100,80,80]]
        self.codes=['#112233','#445566','#778899']
        for (x,y,w,h),color in zip(self.cards,[(17,34,51),(68,85,102),(119,136,153)]):
            self.image[y:y+h,x:x+w]=color
        self.scene=SimpleNamespace(cards=self.cards,markers=[(140,300),(340,300),(540,300)],board=[40,200,640,800])
        self.calls=[]
        self.cache={}

    def glyphs(self,image,card,**unused):
        index=self.scene.cards.index(list(card));self.calls.append(index)
        return dict(hex=self.codes[index],glyphs_unambiguous=True,method='test_screenshot_text')

    def read(self,image=None,**kwargs):
        # The absent optional cache must fail on repeated recognition behavior,
        # rather than turning the pre-implementation red run into TypeError.
        if 'card_cache' in inspect.signature(io.read_probe_frame).parameters:
            kwargs['card_cache']=self.cache
        with patch.object(io,'recognize',return_value=self.scene):
            return io.read_probe_frame(self.image if image is None else image,deadline=100.,clock=lambda:1.,
                hex_fallback=self.glyphs,timer_mode='skip',**kwargs)

    def test_identical_cards_reuse_screenshot_hex_but_remeasure_new_frame(self):
        with patch.object(io,'recognize',return_value=self.scene) as recognition:
            kwargs=dict(deadline=100.,clock=lambda:1.,hex_fallback=self.glyphs,timer_mode='skip')
            if 'card_cache' in inspect.signature(io.read_probe_frame).parameters:kwargs['card_cache']=self.cache
            first=io.read_probe_frame(self.image,**kwargs)
            second=io.read_probe_frame(self.image.copy(),**kwargs)
        self.assertEqual(first['hex'],self.codes)
        self.assertEqual(second['hex'],self.codes)
        self.assertEqual(self.calls,[0,1,2],'An identical new screenshot must not rerun text recognition')
        self.assertEqual(recognition.call_count,2)
        self.assertEqual(second.get('hex_cache_hits'),[True,True,True])

    def test_one_changed_pixel_outside_swatch_rechecks_only_that_whole_card(self):
        self.read();changed=self.image.copy();changed[100,300,0]+=1
        result=self.read(changed)
        self.assertEqual(result['hex'],self.codes)
        self.assertEqual(self.calls,[0,1,2,1])
        self.assertEqual(result.get('hex_cache_hits'),[True,False,True])

    def test_same_rgb_bytes_with_different_card_shape_are_not_a_cache_hit(self):
        self.read()
        changed=self.image.copy();changed[100:260,100:140]=(17,34,51)
        self.scene.cards[0]=[100,100,40,160]
        result=self.read(changed)
        self.assertEqual(result['hex'],self.codes)
        self.assertEqual(self.calls,[0,1,2,0])
        self.assertEqual(result.get('hex_cache_hits'),[False,True,True])

    def test_invalid_or_swatch_disagreeing_cached_hex_is_rechecked(self):
        for bad in ('#11223Z','#aabbcc','#FFFFFF',None):
            with self.subTest(bad=bad):
                self.cache={};self.calls=[];self.read()
                for key in list(self.cache):self.cache[key]=bad
                result=self.read()
                self.assertEqual(result['hex'],self.codes)
                self.assertEqual(self.calls,[0,1,2,0,1,2])
                self.assertEqual(result.get('hex_cache_hits'),[False,False,False])

    def test_failed_screenshot_read_is_not_populated_by_native_fill(self):
        def missing(image,card,**unused):return dict(hex=None,glyphs_unambiguous=False)
        kwargs=dict(deadline=100.,clock=lambda:1.,hex_fallback=missing,timer_mode='skip')
        if 'card_cache' in inspect.signature(io.read_probe_frame).parameters:kwargs['card_cache']=self.cache
        with patch.object(io,'recognize',return_value=self.scene),patch.object(io,'read_codes',return_value=[None]*3):
            missing_frame=io.read_probe_frame(self.image,**kwargs)
        filled=io.merge_native_hex(missing_frame,self.codes)
        self.assertEqual(filled['hex_source'],['native_checkpoint']*3)
        self.assertEqual(self.cache,{})
        result=self.read()
        self.assertEqual(result['hex'],self.codes)
        self.assertEqual(result.get('hex_cache_hits'),[False]*3)

    def test_cache_stays_bounded_when_card_pixels_keep_changing(self):
        for value in range(100):
            changed=self.image.copy();changed[100,100,0]=value
            self.read(changed)
        self.assertLessEqual(len(self.cache),96)
        self.assertGreater(len(self.cache),3,'Distinct card images should be retained until the bound')
        self.calls=[];oldest=self.image.copy();oldest[100,100,0]=0;self.read(oldest)
        self.assertIn(0,self.calls,'The oldest changing-card image should have been evicted')

    def test_cache_hit_still_checks_cancel_and_deadline(self):
        self.read()
        def stopped():raise InterruptedError('F9')
        with self.assertRaises(InterruptedError):self.read(check=stopped)
        kwargs=dict(deadline=0.,clock=lambda:1.,hex_fallback=self.glyphs,timer_mode='skip')
        if 'card_cache' in inspect.signature(io.read_probe_frame).parameters:kwargs['card_cache']=self.cache
        with patch.object(io,'recognize',return_value=self.scene),self.assertRaises(TimeoutError):
            io.read_probe_frame(self.image,**kwargs)

    def test_project_io_captures_all_four_frames_and_keeps_native_crosscheck(self):
        observation=dict(session_token=['session'],process_identity=[1,2,3,'build'],
            motion=dict(binding={},settings={}),window_context=dict(window=dict(client_size_physical=[1280,960])),
            window_mapping_candidate=dict(client_board_candidate=[40,200,640,800]))
        baseline=dict(session_deadline_monotonic=float('inf'),baseline=observation)
        captures=[]
        def capture():captures.append(True);return self.image.copy()
        game=SimpleNamespace(check=lambda:None,capture=capture)
        with tempfile.TemporaryDirectory() as folder:
            project=io.ProjectProbeIO(None,baseline,folder,game=game,f9_pressed=lambda:False)
            project.check=lambda deadline:None;project._input_guard=lambda:None
            project.last_client_hex=list(self.codes);project.hex_fallback=self.glyphs;project.timer_grace_until=float('inf')
            with patch.object(io,'_recognize_native_layout',return_value=self.scene):
                initial=project.frames('initial',float('inf'))
                revalidate=project.frames('revalidate',float('inf'))
                project.last_client_hex=['#000000']*3
                with self.assertRaisesRegex(ValueError,'Screenshot and checkpoint HEX disagree'):
                    project.frames('mismatch',float('inf'))
            self.assertEqual(len(captures),5)
            self.assertEqual(self.calls,[0,1,2])
            self.assertEqual([f['hex'] for f in [*initial,*revalidate]],[self.codes]*4)
            self.assertEqual([f.get('hex_cache_hits') for f in revalidate],[[True]*3]*2)
            self.assertTrue(all(f['screenshot_hex_verified'] for f in revalidate))


if __name__=='__main__':unittest.main()
