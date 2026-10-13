"""Color conflicts need independent screenshot text, never expected-digit repair."""
from contextlib import ExitStack
import copy
import hashlib
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from PIL import Image
from native_live import project_probe_io as probe
import test_native_probe_card_cache as cache_fixture


class NativeHexConflictTests(unittest.TestCase):
    def project(self,folder,cleanup):
        fixture=cache_fixture.ProbeCardCacheTests();fixture.setUp()
        # The last glyph differs by only two in RGB, so both plausible OCR
        # codes pass the old swatch gate; the pixels must decide the character.
        fixture.codes=['#112233','#445566','#72514A']
        fixture.image[100:180,500:580]=(114,81,73)
        observation=dict(session_token=['session'],process_identity=[1,2,3,'build'],
            motion=dict(binding={},settings={}),window_context=dict(window=dict(client_size_physical=[1280,960])),
            window_mapping_candidate=dict(client_board_candidate=[40,200,640,800]))
        io=probe.ProjectProbeIO(None,dict(session_deadline_monotonic=float('inf'),baseline=observation),folder,
            game=SimpleNamespace(check=lambda:None,capture=lambda:fixture.image.copy()),f9_pressed=lambda:False)
        io.check=lambda deadline:None;io._input_guard=lambda:None;io.last_client_hex=fixture.codes
        cleanup.callback(io.release)
        io.timer_grace_until=float('inf')
        decoded=dict(hex=['#112233','#445566','#725148'],cards=fixture.cards,markers=fixture.scene.markers,
            visual_board=fixture.scene.board,remaining_seconds=None,hex_cache_hits=[False]*3)
        return io,fixture,decoded

    def test_different_threshold_text_resolves_a_plausible_low_nibble_misread(self):
        with tempfile.TemporaryDirectory() as folder,ExitStack() as cleanup:
            io,fixture,decoded=self.project(folder,cleanup);calls=[]
            def text(image,cards,**kwargs):
                self.assertEqual(cards,[fixture.cards[2]])
                self.assertFalse(any('native' in key or 'expected' in key for key in kwargs))
                calls.append(True)
                return ['#72514A'],[dict(reads=[dict(hex='#72514A')]*2)]
            with patch.object(probe,'read_probe_frame',side_effect=lambda *a,**kw:copy.deepcopy(decoded)), \
                 patch('screenshot_text.read_visible',side_effect=text):
                rows=io.frames('endpoint',float('inf'))
            self.assertEqual(len(calls),2)
            self.assertTrue(all(row['screenshot_hex']==fixture.codes and row['screenshot_hex_verified'] for row in rows))
            self.assertEqual(rows[0]['hex_conflict_reads'][0]['original_hex'],'#725148')

    def test_failed_adjudication_does_not_fill_expected_digits_and_saves_evidence(self):
        for result in (None,'#725148'):
            with self.subTest(result=result),tempfile.TemporaryDirectory() as folder,ExitStack() as cleanup:
                io,fixture,decoded=self.project(folder,cleanup)
                with patch.object(probe,'read_probe_frame',side_effect=lambda *a,**kw:copy.deepcopy(decoded)), \
                     patch('screenshot_text.read_visible',return_value=([result],[dict(reads=[])])):
                    with self.assertRaisesRegex(ValueError,'Screenshot and checkpoint HEX disagree'):
                        io.frames('conflict',float('inf'))
                evidence=Path(folder)/'conflict_frame0.decoded.json'
                self.assertTrue(evidence.is_file())
                saved=json.loads(evidence.read_text(encoding='utf-8'))
                self.assertEqual(saved['hex'][2],'#725148')
                self.assertFalse(saved.get('screenshot_hex_verified',False))

    def test_disproved_card_cache_is_evicted_and_only_confirmed_text_is_stored(self):
        for confirmed in (None,'#72514A'):
            with self.subTest(confirmed=confirmed),tempfile.TemporaryDirectory() as folder,ExitStack() as cleanup:
                io,fixture,decoded=self.project(folder,cleanup)
                card=fixture.cards[2];x,y,w,h=card;pixels=fixture.image[y:y+h,x:x+w]
                key=(pixels.shape,hashlib.sha256(pixels.tobytes()).hexdigest())
                io.card_cache[key]='#725148'
                decoded['hex_cache_hits'][2]=True
                with patch.object(probe,'read_probe_frame',side_effect=lambda *a,**kw:copy.deepcopy(decoded)), \
                     patch('screenshot_text.read_visible',return_value=([confirmed],[dict(reads=[])])):
                    if confirmed:io.frames('cached',float('inf'))
                    else:
                        with self.assertRaises(ValueError):io.frames('cached',float('inf'))
                self.assertEqual(io.card_cache.get(key),confirmed)

    def test_stop_or_deadline_during_conflict_read_is_not_suppressed(self):
        for error in (InterruptedError('F9'),TimeoutError('actual deadline')):
            with self.subTest(error=type(error).__name__),tempfile.TemporaryDirectory() as folder,ExitStack() as cleanup:
                io,fixture,decoded=self.project(folder,cleanup)
                with patch.object(probe,'read_probe_frame',side_effect=lambda *a,**kw:copy.deepcopy(decoded)), \
                     patch('screenshot_text.read_visible',side_effect=error):
                    with self.assertRaises(type(error)):io.frames('stopped',float('inf'))

    def test_diagnostic_write_failure_does_not_replace_stop_or_deadline(self):
        for error in (InterruptedError('F9'),TimeoutError('actual deadline')):
            with self.subTest(error=type(error).__name__),tempfile.TemporaryDirectory() as folder,ExitStack() as cleanup:
                io,fixture,decoded=self.project(folder,cleanup)
                with patch.object(probe,'read_probe_frame',side_effect=lambda *a,**kw:copy.deepcopy(decoded)), \
                     patch('screenshot_text.read_visible',side_effect=error), \
                     patch.object(Path,'write_text',side_effect=OSError('disk full')):
                    with self.assertRaises(type(error)):io.frames('stopped',float('inf'))

    def test_confirmed_text_outside_original_swatch_tolerance_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as folder,ExitStack() as cleanup:
            io,fixture,decoded=self.project(folder,cleanup)
            fixture.image[100:180,500:580]=(120,81,73)
            with patch.object(probe,'read_probe_frame',side_effect=lambda *a,**kw:copy.deepcopy(decoded)), \
                 patch('screenshot_text.read_visible',return_value=(['#72514A'],[dict(reads=[])])):
                with self.assertRaisesRegex(ValueError,'Screenshot and checkpoint HEX disagree'):
                    io.frames('swatch',float('inf'))
            self.assertEqual(io.card_cache,{})

    def test_matching_frames_keep_fast_path_without_second_text_reader(self):
        with tempfile.TemporaryDirectory() as folder,ExitStack() as cleanup:
            io,fixture,decoded=self.project(folder,cleanup);decoded['hex']=fixture.codes
            with patch.object(probe,'read_probe_frame',side_effect=lambda *a,**kw:copy.deepcopy(decoded)), \
                 patch('screenshot_text.read_visible',side_effect=AssertionError('No conflict needs rereading')):
                frames=io.frames('matching',float('inf'))
            self.assertTrue(all(frame['screenshot_hex_verified'] for frame in frames))


class RecordedHexConflictTests(unittest.TestCase):
    def test_actual_rc8_a_is_not_replaced_by_a_plausible_eight(self):
        from vision import configure_ocr
        from native_live.dye_hex_glyphs import read_card_glyphs
        configure_ocr(strict=True)
        fixture=Path(__file__).resolve().parents[2]/'fixtures/native-hex-conflict/cards.png'
        image=np.array(Image.open(fixture).convert('RGB'))
        cards=[[17,10,80,80],[181,10,80,80],[346,10,79,79]]
        scene=SimpleNamespace(cards=cards,markers=[(57,90),(221,90),(385,90)],board=[0,0,438,95])
        with patch.object(probe,'recognize',return_value=scene), \
                patch('vision._tesseract',side_effect=AssertionError('Game font resolves this recorded failure')):
            decoded=probe.read_probe_frame(image,deadline=time.monotonic()+8.,
                hex_fallback=read_card_glyphs,timer_mode='skip')
        expected=['#F27233','#EAD310','#72514A']
        self.assertEqual(decoded['hex'],expected)
        corrected=probe.reread_conflicting_hex(image,decoded,expected,deadline=time.monotonic()+5.)
        merged=probe.merge_native_hex(corrected,expected)
        self.assertEqual(merged['screenshot_hex'],expected)
        self.assertTrue(merged['screenshot_hex_verified'])
        self.assertEqual(merged['hex_conflict_reads'],[])


if __name__=='__main__':unittest.main()
