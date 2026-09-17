import unittest,tempfile
from unittest.mock import patch,MagicMock
import numpy as np
from engine import Runner,local_offsets,actual_score
from platform_win import Interrupted
from vision import Scene,lab,rgb
from palette import allowed_colors,mosaic

class ExplorationTests(unittest.TestCase):
    def test_hex_local_refinement_stops_only_after_all_regions_pass(self):
        im=np.zeros((100,100,3),np.uint8);game=MagicMock();game.capture.return_value=im
        rules=[dict(enabled=True,colors=['#808080'],exact=False,tolerance=4)]*3
        before=Scene([],[(20,40),(50,50),(80,60)],(0,0,100,100),['#707070','#808080','#808080'],110,None)
        after=Scene([],before.markers,before.board,['#808080']*3,109,None)
        self.assertGreater(actual_score(before.colors,rules),1)
        with tempfile.TemporaryDirectory() as folder,patch('engine.time.sleep'),patch('engine.recognize',return_value=after):
            _,result=Runner(lambda *args:None,folder).refine_actual(game,im,before,rules,float('inf'))
        self.assertEqual(result.colors,after.colors)
        game.drag.assert_called_once_with(before.board,1,0)
        game.click.assert_not_called()

    def test_failed_local_trial_exits_without_spending_time_on_undo(self):
        im=np.zeros((100,100,3),np.uint8);game=MagicMock();game.capture.return_value=im
        rules=[dict(enabled=True,colors=['#808080'],exact=False,tolerance=4)]*3
        before=Scene([],[(20,40),(50,50),(80,60)],(0,0,100,100),['#707070']*3,110,None)
        bad=Scene([],before.markers,before.board,['#000000']*3,109,None)
        motion=dict(matrix=[[1,0,-2],[0,1,0]],origin=[0,0],angle=0,scale=1)
        with tempfile.TemporaryDirectory() as folder,patch('engine.time.sleep'),patch('engine.recognize',side_effect=[bad,bad]),patch('engine.measure_board_motion',return_value=motion):
            _,result=Runner(lambda *args:None,folder).refine_actual(game,im,before,rules,float('inf'))
        self.assertEqual(result.colors,bad.colors)
        game.drag.assert_called_once_with(before.board,1,0)
        game.click.assert_not_called()
    def test_local_refinement_covers_neighborhood_without_zero_moves(self):
        points=local_offsets(2)
        self.assertEqual(set(points),{(x,y) for x in range(-2,3) for y in range(-2,3)}-{(0,0)})
        self.assertEqual(len(points),24)
        previous=(0,0)
        for point in points:
            self.assertNotEqual(point,previous)
            self.assertLessEqual(max(abs(point[i]-previous[i]) for i in range(2)),2)
            previous=point
    def test_apply_waits_for_result_animation(self):
        im=np.zeros((100,100,3),np.uint8);game=MagicMock();game.capture.return_value=im
        colors=['#FFFFFF','#848484','#BE9953']
        with tempfile.TemporaryDirectory() as folder,patch('engine.time.sleep'),patch('engine.green_buttons',side_effect=[[],[],[(50,90,40,10)]]),patch('engine.result_colors',side_effect=[colors,None]):
            Runner(lambda *args:None,folder).apply_result(game,im,colors)
        game.click.assert_called_once_with((50,90))

    def test_apply_never_clicks_if_result_changes(self):
        im=np.zeros((100,100,3),np.uint8);game=MagicMock();game.capture.return_value=im
        with tempfile.TemporaryDirectory() as folder,patch('engine.time.sleep'),patch('engine.green_buttons',return_value=[(50,90,40,10)]),patch('engine.result_colors',return_value=['#000000']*3):
            with self.assertRaises(RuntimeError):Runner(lambda *args:None,folder).apply_result(game,im,['#FFFFFF']*3)
        game.click.assert_not_called()

    def test_preview_exact_set_and_unique_colors(self):
        pixels=allowed_colors('#202020',1)
        self.assertGreater(len(pixels),1)
        self.assertEqual(len(pixels),len(np.unique(pixels,axis=0)))
        self.assertTrue(np.all(np.linalg.norm(lab(pixels)-lab([rgb('#202020')])[0],axis=1)<=1))
        # Independent exhaustive local RGB cube: no admissible local color is omitted.
        cube=np.indices((25,25,25)).reshape(3,-1).T+20
        expected=cube[np.linalg.norm(lab(cube)-lab([rgb('#202020')])[0],axis=1)<=1]
        actual={tuple(p) for p in pixels}
        self.assertTrue(all(tuple(p) in actual for p in expected))
        im,pages=mosaic(np.array([[32,32,32]],np.uint8))
        self.assertTrue(np.all(np.asarray(im)==32));self.assertEqual(pages,1)

    def test_mosaic_single_page_density_never_blends_colors(self):
        values=np.arange(16000,dtype=np.uint32)
        colors=np.column_stack(((values>>16)&255,(values>>8)&255,values&255)).astype(np.uint8)
        im,pages=mosaic(colors)
        self.assertEqual(pages,1)
        found=set(map(tuple,np.asarray(im).reshape(-1,3)))
        expected=set(map(tuple,colors))
        self.assertTrue(found.issubset(expected))
        self.assertIn(tuple(colors[-1]),found)
        self.assertEqual(tuple(np.asarray(im)[32,120]),tuple(colors[0]))

    def test_radial_preview_delta_increases_outward(self):
        pixels=allowed_colors('#808080',1)
        im,pages=mosaic(pixels);arr=np.asarray(im)
        self.assertEqual(pages,1)
        self.assertEqual(tuple(arr[32,120]),(128,128,128))
        self.assertLess(np.linalg.norm(lab([arr[32,120]])-lab([[128,128,128]])),np.linalg.norm(lab([arr[0,0]])-lab([[128,128,128]])))
        self.assertTrue(set(map(tuple,pixels)).issubset(set(map(tuple,arr.reshape(-1,3)))))

    def test_missing_candidate_causes_multiple_real_drag_calls(self):
        self.run_search(None)

    def test_accepted_similarity_keeps_exploring_instead_of_finishing(self):
        game=MagicMock();game.hwnd=1
        frames=[np.full((100,100,3),i*20,np.uint8) for i in range(4)]
        game.capture.side_effect=frames+[Interrupted('test complete')]
        scene=Scene([],[(20,40),(50,50),(80,60)],(0,0,100,100),['#FEFEFE']*3,110,None)
        rules=[dict(enabled=True,colors=['#FFFFFF'],exact=False,tolerance=12)]*3
        events=[]
        with tempfile.TemporaryDirectory() as folder,patch('engine.Game',return_value=game),patch('engine.configure_ocr'),patch('engine.result_colors',return_value=None),patch('engine.recognize',return_value=scene),patch('engine.candidate_shift',return_value=(0,0,.1)),patch('engine.time.sleep'),patch('platform_win.u.GetDpiForWindow',return_value=96):
            Runner(lambda k,d:events.append((k,d)),folder).launch(rules,auto=True)
        self.assertGreaterEqual(game.drag.call_count,3)
        self.assertFalse(any(k=='match' for k,d in events))
        game.click.assert_not_called()

    def test_distant_candidate_triggers_exploration(self):
        self.run_search((12,12,90.0))

    def test_exploration_keeps_rotation_and_zoom_available(self):
        game=self.run_search(None,frames_count=17)
        self.assertGreaterEqual(game.rotate.call_count,2)
        self.assertGreaterEqual(game.wheel.call_count,2)

    def test_read_on_result_page_never_applies_even_when_auto_enabled(self):
        game=MagicMock();game.hwnd=1;game.capture.return_value=np.zeros((100,100,3),np.uint8)
        rules=[{'enabled':True,'colors':['#010203'],'exact':True}]*3
        with tempfile.TemporaryDirectory() as folder,patch('engine.Game',return_value=game),patch('engine.configure_ocr'),patch('engine.result_colors',return_value=['#010203']*3),patch('platform_win.u.GetDpiForWindow',return_value=96):
            Runner(lambda *args:None,folder).launch(rules,'read',True)
        game.click.assert_not_called()

    def run_search(self,candidate,frames_count=6):
        game=MagicMock();game.hwnd=1
        frames=[np.full((100,100,3),(i*20)%256,np.uint8) for i in range(frames_count)]
        game.capture.side_effect=frames+[Interrupted('test complete')]
        scene=Scene([],[(20,40),(50,50),(80,60)],(0,0,100,100),[None]*3,110,None)
        events=[]
        rules=[{'enabled':True,'colors':['#010203'],'exact':True,'tolerance':0}]+[{'enabled':False}]*2
        with tempfile.TemporaryDirectory() as folder,patch('engine.Game',return_value=game),patch('engine.configure_ocr'),patch('engine.result_colors',return_value=None),patch('engine.recognize',return_value=scene),patch('engine.candidate_shift',return_value=candidate),patch('engine.time.sleep'),patch('platform_win.u.GetDpiForWindow',return_value=96):
            Runner(lambda k,d:events.append((k,d)),folder).launch(rules)
        self.assertGreaterEqual(game.drag.call_count,3)
        self.assertGreaterEqual(sum(k=='explore' for k,d in events),3)
        game.click.assert_not_called()
        return game

if __name__=='__main__':unittest.main()
