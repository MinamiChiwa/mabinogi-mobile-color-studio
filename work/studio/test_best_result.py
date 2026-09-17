import unittest,tempfile,time
from unittest.mock import patch,MagicMock
import numpy as np
from PIL import Image
from best_result import BestResult,proximity,global_matrix
from vision import Scene
from engine import Runner,perfect_match
from eyedropper import pixel_hex

class BestResultTests(unittest.TestCase):
    def test_similarity_hit_does_not_end_optimization(self):
        rules=[dict(enabled=True,colors=['#FFFFFF','#000000'],exact=False,tolerance=12),dict(enabled=False)]
        self.assertFalse(perfect_match(['#FEFEFE',None],rules))
        self.assertTrue(perfect_match(['#ffffff',None],rules))
        self.assertTrue(perfect_match(['#000000',None],rules))
        self.assertFalse(perfect_match([None,None],rules))
    def rules(self):return [dict(enabled=True,colors=['#FFFFFF'],exact=True,tolerance=0)]+[dict(enabled=False)]*2
    def scene(self,color):return Scene([],[(30,40),(60,50),(90,60)],(0,0,120,120),[color,None,None],14,None)
    def test_best_rank_uses_actual_colors_and_ignores_disabled_regions(self):
        self.assertLess(proximity(['#FEFEFE',None,None],self.rules()),proximity(['#AAAAAA',None,None],self.rules()))
        rules=self.rules();rules[0]['colors'].append('#000000')
        self.assertEqual(proximity(['#000000',None,None],rules),(0,0))
        self.assertTrue(np.isinf(proximity([None]*3,rules)[0]))
    def test_pose_chain_can_restore_when_direct_overlap_lost(self):
        tracker=BestResult(self.rules());a=np.zeros((120,120,3),np.uint8)
        tracker.observe(a,self.scene('#FEFEFE'))
        motion=dict(matrix=[[0,-1,50],[1,0,20]],origin=[10,30])
        with patch('best_result.measure_board_motion',side_effect=[motion,None]):
            tracker.observe(a.copy(),self.scene('#AAAAAA'))
            restore=tracker.restoration(a, self.scene('').board)
        np.testing.assert_allclose(restore@global_matrix(motion),np.eye(3),atol=1e-10)
    def test_uncertain_pose_does_not_invent_restoration(self):
        tracker=BestResult(self.rules());a=np.zeros((120,120,3),np.uint8)
        tracker.observe(a,self.scene('#FEFEFE'))
        with patch('best_result.measure_board_motion',return_value=None):
            tracker.observe(a.copy(),self.scene('#AAAAAA'))
            self.assertIsNone(tracker.restoration(a,self.scene('').board))
    def test_recorded_drag_remains_recoverable_after_visual_tracking_loss(self):
        tracker=BestResult(self.rules());a=np.zeros((120,120,3),np.uint8)
        tracker.observe(a,self.scene('#FEFEFE'));tracker.expect({'dx':30,'dy':-20})
        with patch('best_result.measure_board_motion',return_value=None):
            tracker.observe(a.copy(),self.scene('#AAAAAA'))
            restore=tracker.restoration(a,self.scene('').board)
        np.testing.assert_allclose(restore,np.array([[1,0,-30],[0,1,20],[0,0,1]]))
        self.assertEqual(tracker.estimated_steps,1)
    def test_compromise_returns_best_without_applying_or_claiming_exact(self):
        im=np.zeros((120,120,3),np.uint8);game=MagicMock();game.capture.return_value=im
        events=[]
        with tempfile.TemporaryDirectory() as folder,patch('engine.time.sleep'),patch('engine.recognize',return_value=self.scene('#FEFEFE')):
            runner=Runner(lambda k,d:events.append((k,d)),folder);runner.best=MagicMock()
            runner.best.colors=['#FEFEFE',None,None];runner.best.score=proximity(runner.best.colors,self.rules())
            runner.best.restoration.return_value=np.array([[1,0,10],[0,1,-5],[0,0,1]])
            runner.restore_best(game,im,self.scene('#AAAAAA'),self.rules(),time.monotonic()+15)
        game.drag.assert_called_once_with((0,0,120,120),10,-5);game.click.assert_not_called()
        result=events[-1][1];self.assertTrue(result['restored']);self.assertTrue(result['popup']);self.assertEqual(result['outcome'],'compromise')
    def test_eyedropper_uses_frozen_pixel_and_clamps_edges(self):
        im=Image.new('RGB',(2,2),(12,34,56));im.putpixel((1,1),(255,128,0))
        self.assertEqual(pixel_hex(im,0,0),'#0C2238');self.assertEqual(pixel_hex(im,20,20),'#FF8000')

if __name__=='__main__':unittest.main()
