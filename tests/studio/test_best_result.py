import unittest,tempfile,time
from unittest.mock import patch,MagicMock
import numpy as np
from PIL import Image
from best_result import BestResult,proximity,global_matrix
from vision import Scene
from engine import Runner,perfect_match
from eyedropper import pixel_hex

class BestResultTests(unittest.TestCase):
    def test_restore_large_scale_before_small_rotation(self):
        im=np.zeros((120,120,3),np.uint8);game=MagicMock();game.capture.return_value=im
        angle=np.radians(1);scale=.5
        matrix=np.eye(3);matrix[:2,:2]=scale*np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
        with tempfile.TemporaryDirectory() as folder,patch('engine.time.sleep'),patch('engine.recognize',return_value=self.scene('#FEFEFE')):
            runner=Runner(lambda *args:None,folder);runner.best=MagicMock()
            runner.best.colors=['#FEFEFE',None,None];runner.best.score=proximity(runner.best.colors,self.rules())
            runner.best.target_rank.return_value=(1,*runner.best.score)
            runner.best.rotation_gain=1.;runner.best.wheel_log_gain=np.log(1.01)
            runner.best.restoration.return_value=matrix
            runner.restore_best(game,im,self.scene('#AAAAAA'),self.rules(),time.monotonic()+30)
        self.assertEqual(game.wheel.call_args.args[1],-32)
        game.rotate.assert_not_called();game.click.assert_not_called()
    def test_cached_motion_updates_pose_without_recomputing(self):
        tracker=BestResult(self.rules());a=np.zeros((120,120,3),np.uint8)
        tracker.observe(a,self.scene('#FEFEFE'))
        tracker.expect({'dx':30,'dy':0,'measured_motion':{'matrix':[[1,0,28],[0,1,2]],'origin':[0,0]}})
        with patch('best_result.measure_board_motion') as estimate:
            tracker.observe(a.copy(),self.scene('#AAAAAA'))
            estimate.assert_not_called()
        np.testing.assert_allclose(tracker.pose[:2,2],[28,2])
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
            runner.best.target_rank.return_value=(1,*runner.best.score)
            runner.best.rotation_gain=1.;runner.best.wheel_log_gain=np.log(1.01)
            runner.best.restoration.return_value=np.array([[1,0,10],[0,1,-5],[0,0,1]])
            runner.restore_best(game,im,self.scene('#AAAAAA'),self.rules(),time.monotonic()+15)
        game.drag.assert_called_once_with((0,0,120,120),10,-5);game.click.assert_not_called()
        result=events[-1][1];self.assertTrue(result['restored']);self.assertTrue(result['popup']);self.assertEqual(result['outcome'],'compromise')
    def test_every_observation_recorded_but_keyframe_memory_bounded(self):
        tracker=BestResult(self.rules());tracker.memory_limit=120*120*3
        a=np.zeros((120,120,3),np.uint8)
        motion=dict(matrix=[[1,0,1],[0,1,0]],origin=[0,0])
        for i in range(25):
            tracker.expect({'dx':1,'dy':0,'measured_motion':motion})
            tracker.observe(a.copy(),self.scene('#FEFEFE' if i==0 else '#AAAAAA'))
        self.assertEqual(len(tracker.records),25)
        self.assertLessEqual(tracker.frame_bytes,tracker.memory_limit)
        self.assertIn(tracker.best_index,tracker.frames)

    def test_long_unmeasured_chain_is_not_treated_as_reliable_pose(self):
        tracker=BestResult(self.rules());a=np.zeros((120,120,3),np.uint8)
        tracker.observe(a,self.scene('#FEFEFE'))
        with patch('best_result.measure_board_motion',return_value=None):
            for _ in range(4):
                tracker.expect({'dx':30,'dy':0,'measured_motion':None})
                tracker.observe(a.copy(),self.scene('#AAAAAA'))
            self.assertIsNone(tracker.restoration(a,self.scene('').board))

    def test_checkpoint_used_when_direct_best_and_pose_unavailable(self):
        tracker=BestResult(self.rules());a=np.zeros((120,120,3),np.uint8)
        tracker.observe(a,self.scene('#FEFEFE'))
        with patch('best_result.measure_board_motion',return_value=None):
            for _ in range(4):tracker.observe(a.copy(),self.scene('#AAAAAA'))
        tracker.begin_restore()
        motion=dict(matrix=[[1,0,-20],[0,1,5]],origin=[0,0])
        with patch('best_result.measure_board_motion',side_effect=[None,motion]):
            matrix=tracker.restoration(a,self.scene('').board)
        self.assertEqual(tracker.last_route,'checkpoint')
        np.testing.assert_allclose(matrix,global_matrix(motion))

    def test_feasible_combination_beats_smaller_but_infeasible_maximum(self):
        from best_result import ranking
        rules=[dict(enabled=True,colors=['#FFFFFF'],exact=False,tolerance=.1),
               dict(enabled=True,colors=['#FFFFFF'],exact=False,tolerance=30),dict(enabled=False)]
        self.assertLess(ranking(['#FFFFFF','#DDDDDD',None],rules),ranking(['#FEFEFE','#EEEEEE',None],rules))

    def test_restore_can_run_beyond_eighteen_actions_while_improving(self):
        im=np.zeros((120,120,3),np.uint8);game=MagicMock();game.capture.return_value=im
        colors=[self.scene('#AAAAAA')]*20+[self.scene('#FEFEFE')]*2
        with tempfile.TemporaryDirectory() as folder,patch('engine.time.sleep'),patch('engine.recognize',side_effect=colors):
            runner=Runner(lambda *args:None,folder);runner.best=MagicMock()
            runner.best.colors=['#FEFEFE',None,None]
            runner.best.target_rank.return_value=(1,*proximity(runner.best.colors,self.rules()))
            runner.best.rotation_gain=1.;runner.best.wheel_log_gain=np.log(1.01)
            runner.best.restoration.side_effect=[np.array([[1,0,100-i*3],[0,1,0],[0,0,1]]) for i in range(21)]
            runner.restore_best(game,im,self.scene('#AAAAAA'),self.rules(),time.monotonic()+30)
        self.assertEqual(game.drag.call_count,21)
        game.click.assert_not_called()

    def test_final_twelve_seconds_send_no_restore_gestures(self):
        im=np.zeros((120,120,3),np.uint8);game=MagicMock();events=[]
        with tempfile.TemporaryDirectory() as folder:
            runner=Runner(lambda k,d:events.append((k,d)),folder);runner.best=BestResult(self.rules())
            runner.best.observe(im,self.scene('#FEFEFE'))
            runner.restore_best(game,im,self.scene('#AAAAAA'),self.rules(),time.monotonic()+11)
        game.drag.assert_not_called();game.wheel.assert_not_called();game.rotate.assert_not_called()
        self.assertFalse(events[-1][1]['restored'])

    def test_close_compromise_stops_after_color_verification(self):
        from engine import recovery_close
        rules=self.rules();im=np.zeros((120,120,3),np.uint8);game=MagicMock();game.capture.return_value=im
        self.assertTrue(recovery_close(['#FDFDFD',None,None],['#FEFEFE',None,None],rules))
        self.assertFalse(recovery_close(['#FEFEFE',None,None],['#FFFFFF',None,None],rules))
        with tempfile.TemporaryDirectory() as folder,patch('engine.recognize',return_value=self.scene('#FDFDFD')):
            runner=Runner(lambda *args:None,folder);runner.best=BestResult(rules)
            runner.best.observe(im,self.scene('#FEFEFE'))
            runner.restore_best(game,im,self.scene('#FDFDFD'),rules,time.monotonic()+30)
        game.drag.assert_not_called();game.wheel.assert_not_called();game.rotate.assert_not_called()

    def test_eyedropper_uses_frozen_pixel_and_clamps_edges(self):
        im=Image.new('RGB',(2,2),(12,34,56));im.putpixel((1,1),(255,128,0))
        self.assertEqual(pixel_hex(im,0,0),'#0C2238');self.assertEqual(pixel_hex(im,20,20),'#FF8000')

if __name__=='__main__':unittest.main()
