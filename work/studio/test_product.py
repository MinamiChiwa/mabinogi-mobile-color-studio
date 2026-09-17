import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from palette import allowed_colors,overview,full_atlas
from engine import exact_zoom_candidate,reconcile_deadline,transform_points,local_stagnation,bounded_zoom
from vision import Scene,lab,rgb,candidate_shift
from result_history import describe_result,save_result,read_history
from unittest.mock import MagicMock
from engine import Runner
from platform_win import Interrupted

class ProductTests(unittest.TestCase):
    def test_wait_accepts_delayed_board_only_after_timer_appears(self):
        game=MagicMock();image=np.zeros((150,150,3),np.uint8);game.capture.return_value=image
        tutorial=Scene([],[],(0,0,150,150),[None]*3,None,None)
        ready=Scene([],[],(0,0,150,150),[None]*3,110,None)
        with tempfile.TemporaryDirectory() as folder,patch('engine.recognize',side_effect=[ValueError('inventory')]*20+[tutorial,ready]):
            runner=Runner(lambda *args:None,folder)
            with patch.object(runner.stop,'wait',return_value=False):
                _,scene=runner.wait_for_board(game,image)
        self.assertIs(scene,ready);self.assertEqual(game.capture_waiting.call_count,21)
        self.assertTrue(any(e['kind']=='waiting' for e in runner.trace))
        game.drag.assert_not_called();game.wheel.assert_not_called();game.click.assert_not_called()

    def test_wait_timeout_is_explicit_and_sends_no_input(self):
        game=MagicMock()
        with tempfile.TemporaryDirectory() as folder,patch('engine.recognize',side_effect=ValueError('inventory')),patch('engine.time.monotonic',side_effect=[0,61]):
            runner=Runner(lambda *args:None,folder)
            with self.assertRaisesRegex(TimeoutError,'尚未开始寻色'):runner.wait_for_board(game,None)
        game.drag.assert_not_called();game.click.assert_not_called()

    def test_wait_survives_hidden_window_and_ocr_timeout(self):
        image=np.zeros((150,150,3),np.uint8);game=MagicMock()
        game.capture_waiting.side_effect=[None,image,image]
        ready=Scene([],[],(0,0,150,150),[None]*3,110,None)
        with tempfile.TemporaryDirectory() as folder,patch('engine.recognize',side_effect=[ValueError('inventory'),RuntimeError('Tesseract process timeout'),ready]):
            runner=Runner(lambda *args:None,folder)
            with patch.object(runner.stop,'wait',return_value=False):
                _,scene=runner.wait_for_board(game,image)
        self.assertIs(scene,ready);self.assertEqual(game.capture_waiting.call_count,3)
        game.drag.assert_not_called();game.click.assert_not_called()

    def test_wait_can_be_cancelled_with_stop_event(self):
        with tempfile.TemporaryDirectory() as folder,patch('engine.recognize',side_effect=ValueError('inventory')):
            runner=Runner(lambda *args:None,folder)
            with patch.object(runner.stop,'wait',return_value=True),self.assertRaises(Interrupted):
                runner.wait_for_board(MagicMock(),None)

    def test_unlimited_wait_survives_more_than_sixty_seconds(self):
        game=MagicMock();image=np.zeros((150,150,3),np.uint8)
        game.capture_waiting.return_value=image
        ready=Scene([],[],(0,0,150,150),[None]*3,110,None)
        with tempfile.TemporaryDirectory() as folder,patch('engine.recognize',side_effect=[ValueError('inventory'),ready]),patch('engine.time.monotonic',side_effect=[0,200]):
            runner=Runner(lambda *args:None,folder)
            with patch.object(runner.stop,'wait',return_value=False):
                _,scene=runner.wait_for_board(game,None,timeout=None)
        self.assertIs(scene,ready)
        self.assertTrue(all(e['seconds'] is None for e in runner.trace if e['kind']=='waiting'))
        game.focus.assert_not_called();game.click.assert_not_called()

    def test_search_bypasses_focus_capture_and_result_page_before_waiting(self):
        game=MagicMock();game.hwnd=1;events=[]
        rules=[dict(enabled=True,colors=['#FFFFFF'],exact=True,tolerance=0)]*3
        with tempfile.TemporaryDirectory() as folder,patch('engine.Game',return_value=game),patch('engine.configure_ocr'),patch('engine.result_colors') as result,patch('platform_win.u.GetDpiForWindow',return_value=96):
            runner=Runner(lambda k,d:events.append(k),folder)
            with patch.object(runner,'wait_for_board',side_effect=Interrupted('cancel')) as wait:
                runner.launch(rules)
            self.assertIsNone(wait.call_args.kwargs['timeout'])
        game.focus.assert_not_called();game.capture.assert_not_called();result.assert_not_called()
        self.assertIn('interrupted',events)

    def test_multi_zoom_stays_close_to_entry_and_best(self):
        self.assertEqual(bounded_zoom(32,40,0),8)
        self.assertEqual(bounded_zoom(32,48,0),0)
        self.assertEqual(bounded_zoom(-32,-40,0),-8)
        self.assertEqual(bounded_zoom(32,0,-40),8)
        self.assertEqual(bounded_zoom(-32,48,0),-32)

    def test_multi_search_does_not_repeat_unresponsive_joint_zoom(self):
        game=MagicMock();game.hwnd=1
        game.capture_waiting.side_effect=game.capture
        game.capture.side_effect=[np.full((150,150,3),i*20,np.uint8) for i in range(9)]+[Interrupted('finished')]
        scene=Scene([],[(40,50),(80,70),(120,80)],(0,0,150,150),['#AAAAAA']*3,110,None)
        rules=[dict(enabled=True,colors=['#FFFFFF'],exact=True,tolerance=0) for _ in range(3)]
        motion=dict(matrix=[[1,0,0],[0,1,0]],origin=[0,0],scale=1,angle=0,inliers=30)
        plan=dict(score=.5,dx=0,dy=0,angle=0,scale=1.2)
        with tempfile.TemporaryDirectory() as folder,patch('engine.Game',return_value=game),patch('engine.configure_ocr'),patch('engine.result_colors',return_value=None),patch('engine.recognize',return_value=scene),patch('engine.candidate_shift',return_value=None),patch('engine.joint_plan',return_value=plan),patch('engine.exact_zoom_candidate') as single_zoom,patch('engine.measure_board_motion',return_value=motion),patch('engine.time.sleep'),patch('platform_win.u.GetDpiForWindow',return_value=96):
            runner=Runner(lambda *args:None,folder);runner.launch(rules)
            single_zoom.assert_not_called()
        actions=[c for c in game.method_calls if c[0] in ('wheel','drag','rotate')]
        self.assertEqual(actions[0][0],'wheel')
        self.assertEqual([c[0] for c in actions[1:3]],['drag','drag'])
        self.assertFalse(any(e['kind']=='error' for e in runner.trace))
    def test_local_improvement_resets_failures_but_noise_does_not(self):
        self.assertEqual(local_stagnation((10,10),(8,8),2),0)
        self.assertEqual(local_stagnation((10,10),(9.95,9.95),2),3)
        self.assertEqual(local_stagnation((10,10),(12,12),2),3)

    def test_failed_island_memory_moves_with_texture(self):
        motion=dict(matrix=[[2,0,3],[0,2,-4]],origin=[10,20])
        self.assertEqual(transform_points([(0,20,30)],motion),[(0,33,36)])
        self.assertEqual(transform_points([(0,20,30)],None),[])
        scene=Scene([],[(50,110),(150,110),(250,110)],(0,0,300,300),[None]*3,100,None)
        rules=[dict(enabled=True,colors=['#FFFFFF'],exact=True,tolerance=0)]+[dict(enabled=False)]*2
        image=np.full((300,300,3),80,np.uint8);image[181:186,61:66]=255;image[40,20]=255
        self.assertEqual(candidate_shift(image,scene,rules,excluded=[(0,63,183)])[0:2],(30,70))

    def test_disabled_cards_do_not_run_ocr(self):
        from vision import read_codes
        image=np.full((120,300,3),255,np.uint8)
        cards=[(0,0,80,80),(100,0,80,80),(200,0,80,80)]
        with patch('vision.pytesseract.image_to_string',return_value='#FFFFFF') as ocr:
            colors=read_codes(image,cards,[(40,100),(140,100),(240,100)],enabled=[True,False,False])
        self.assertEqual(colors,['#FFFFFF',None,None]);self.assertEqual(ocr.call_count,1)

    def test_timer_digit_loss_does_not_trigger_early_fallback(self):
        self.assertEqual(reconcile_deadline(200,10,90),200)
        self.assertEqual(reconcile_deadline(200,109,90),199)
        self.assertEqual(reconcile_deadline(200,None,90),200)
    def test_exact_visible_target_is_moved_before_magnification(self):
        scene=Scene([],[(50,110),(150,110),(250,110)],(0,0,300,300),[None]*3,100,None)
        rules=[dict(enabled=True,colors=['#FFFFFF'],exact=True,tolerance=0)]+[dict(enabled=False)]*2
        image=np.full((300,300,3),80,np.uint8)
        image[40,20]=255
        image[180:187,60:67]=255
        move=candidate_shift(image,scene,rules)
        self.assertEqual(move,(-13,-73,0.0))
        self.assertIsNone(exact_zoom_candidate(image,scene,rules))
        image[180:187,60:67]=80
        self.assertEqual(candidate_shift(image,scene,rules),(30,70,0.0))
    def test_zoom_limit_exits_after_three_failed_attempts(self):
        game=MagicMock();game.hwnd=1
        game.capture_waiting.side_effect=game.capture
        game.capture.side_effect=[np.full((150,150,3),i*25,np.uint8) for i in range(8)]+[Interrupted('finished')]
        scene=Scene([],[(40,50),(80,70),(120,80)],(0,0,150,150),['#AAAAAA',None,None],110,None)
        rules=[dict(enabled=True,colors=['#FFFFFF'],exact=True,tolerance=0)]+[dict(enabled=False)]*2
        motion=dict(matrix=[[1,0,0],[0,1,0]],origin=[0,0],scale=1,angle=0,inliers=30)
        with tempfile.TemporaryDirectory() as folder,patch('engine.Game',return_value=game),patch('engine.configure_ocr'),patch('engine.result_colors',return_value=None),patch('engine.recognize',return_value=scene),patch('engine.candidate_shift',return_value=(12,12,10)),patch('engine.measure_board_motion',return_value=motion),patch('engine.time.sleep'),patch('platform_win.u.GetDpiForWindow',return_value=96):
            Runner(lambda *args:None,folder).launch(rules)
        actions=[c for c in game.method_calls if c[0] in ('wheel','drag')]
        self.assertEqual(actions[0][0],'wheel')
        self.assertEqual(actions[0].args[1],32)
        self.assertEqual([c[0] for c in actions[1:4]],['drag']*3)
        self.assertEqual(actions[4][0],'wheel')
        self.assertEqual(actions[4].args[1],-32)
        self.assertEqual([c[0] for c in actions[5:7]],['drag']*2)
    def test_zoom_tracks_original_island_before_reset_and_wide_search(self):
        game=MagicMock();game.hwnd=1
        game.capture_waiting.side_effect=game.capture
        game.capture.side_effect=[np.full((150,150,3),i*17,np.uint8) for i in range(11)]+[Interrupted('finished')]
        scene=Scene([],[(40,50),(80,70),(120,80)],(0,0,150,150),['#AAAAAA',None,None],110,None)
        rules=[dict(enabled=True,colors=['#FFFFFF'],exact=True,tolerance=0)]+[dict(enabled=False)]*2
        def motion(*args):
            actions=[c for c in game.method_calls if c[0] in ('wheel','drag')]
            action=actions[-1]
            scale=1.01**action.args[1] if action[0]=='wheel' else 1
            return dict(matrix=[[scale,0,0],[0,scale,0]],origin=[0,0],scale=scale,angle=0,inliers=30)
        with tempfile.TemporaryDirectory() as folder,patch('engine.Game',return_value=game),patch('engine.configure_ocr'),patch('engine.result_colors',return_value=None),patch('engine.recognize',return_value=scene),patch('engine.candidate_shift',return_value=(12,12,10)),patch('engine.measure_board_motion',side_effect=motion),patch('engine.time.sleep'),patch('platform_win.u.GetDpiForWindow',return_value=96):
            Runner(lambda *args:None,folder).launch(rules)
        actions=[c for c in game.method_calls if c[0] in ('wheel','drag')]
        self.assertEqual([c[0] for c in actions[:7]],['wheel','drag','drag','drag','wheel','drag','drag'])
        self.assertEqual([actions[i].args[1] for i in (0,4)],[32,-32])
        # The original (28,38) island is transformed by the measured zoom,
        # then aligned to marker (40,50), rather than reusing (12,12).
        expected=np.rint(np.array([40,50])-np.array([28,38])*1.01**32).astype(int)
        self.assertEqual(actions[1].args[1:],tuple(expected))

    def test_translations_preserve_hex_and_mode_identifiers(self):
        import i18n
        original=i18n.language
        try:
            i18n.language='English'
            self.assertEqual(i18n.tr('精准 HEX'),'Exact HEX')
            self.assertIn('#FFFFFF',i18n.tr('当前颜色  #FFFFFF'))
            self.assertEqual(i18n.tr('繁體中文'),'繁體中文')
            i18n.language='繁體中文'
            self.assertEqual(i18n.tr('寻色记录'),'尋色記錄')
        finally:i18n.language=original

    def test_exact_magnification_uses_source_island_not_marker(self):
        scene=Scene([],[(40,50),(80,70),(120,80)],(0,0,150,150),[None]*3,100,None)
        rules=[dict(enabled=True,colors=['#FFFFFF'],exact=True,tolerance=0)]+[dict(enabled=False)]*2
        with patch('engine.candidate_shift',return_value=(12,-20,10)):
            self.assertEqual(exact_zoom_candidate(None,scene,rules),(10,0,[28,70]))
        with patch('engine.candidate_shift',return_value=(12,-20,21)):
            self.assertIsNone(exact_zoom_candidate(None,scene,rules))
        rules[0]['exact']=False
        with patch('engine.candidate_shift') as find:
            self.assertIsNone(exact_zoom_candidate(None,scene,rules));find.assert_not_called()
    def test_preview_only_contains_allowed_colors_and_keeps_center(self):
        colors=allowed_colors('#808080',4);im=np.array(overview(colors))
        self.assertEqual(tuple(im[32,120]),(128,128,128))
        self.assertTrue(set(map(tuple,im.reshape(-1,3))).issubset(set(map(tuple,colors))))
        # Overview should use visible squares instead of per-pixel noise.
        self.assertTrue(np.array_equal(im[0,0],im[0,1]))
        distances=np.linalg.norm(lab(im.reshape(-1,3))-lab([rgb('#808080')])[0],axis=1).reshape(64,240)
        self.assertLess(distances[24:40,100:140].mean(),distances[:8].mean())
    def test_full_atlas_preserves_every_color(self):
        colors=allowed_colors('#808080',4);actual=set(map(tuple,np.array(full_atlas(colors)).reshape(-1,3)))
        self.assertEqual(actual,set(map(tuple,colors)))
    def test_history_retains_result_targets_and_real_delta(self):
        rules=[dict(enabled=True,colors=['#FFFFFF','#000000'])]+[dict(enabled=False)]*2
        data=describe_result(['#FEFEFE',None,None],rules)
        self.assertGreater(data['maximum'],0);self.assertLess(data['maximum'],1)
        self.assertEqual(data['maximum'],data['average'])
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'history.json'
            save_result(path,['#FEFEFE',None,None],rules,'compromise',True)
            row=read_history(path)[0]
            self.assertTrue(row['restored']);self.assertEqual(row['regions'][0]['targets'],['#FFFFFF','#000000'])

if __name__=='__main__':unittest.main()
