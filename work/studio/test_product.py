import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from palette import allowed_colors,overview,full_atlas
from engine import exact_zoom_candidate
from vision import Scene,lab,rgb
from result_history import describe_result,save_result,read_history
from unittest.mock import MagicMock
from engine import Runner
from platform_win import Interrupted

class ProductTests(unittest.TestCase):
    def test_zoom_limit_keeps_magnified_view_for_targeting(self):
        game=MagicMock();game.hwnd=1
        game.capture.side_effect=[np.full((150,150,3),i*25,np.uint8) for i in range(8)]+[Interrupted('finished')]
        scene=Scene([],[(40,50),(80,70),(120,80)],(0,0,150,150),['#AAAAAA',None,None],110,None)
        rules=[dict(enabled=True,colors=['#FFFFFF'],exact=True,tolerance=0)]+[dict(enabled=False)]*2
        motion=dict(matrix=[[1,0,0],[0,1,0]],origin=[0,0],scale=1,angle=0,inliers=30)
        with tempfile.TemporaryDirectory() as folder,patch('engine.Game',return_value=game),patch('engine.configure_ocr'),patch('engine.result_colors',return_value=None),patch('engine.recognize',return_value=scene),patch('engine.candidate_shift',return_value=(12,12,10)),patch('engine.measure_board_motion',return_value=motion),patch('engine.time.sleep'),patch('platform_win.u.GetDpiForWindow',return_value=96):
            Runner(lambda *args:None,folder).launch(rules)
        self.assertEqual(game.wheel.call_count,1)
        self.assertGreaterEqual(game.drag.call_count,5)
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
