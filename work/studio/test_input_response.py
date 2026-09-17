import unittest
from types import SimpleNamespace
import numpy as np
from input_response import assess_response,ResponseGuard,Response

class InputResponseTests(unittest.TestCase):
    def setUp(self):
        self.image=np.random.default_rng(7).integers(20,200,(120,120,3),dtype=np.uint8)
        self.scene=SimpleNamespace(board=(0,0,120,120),markers=[(20,40),(60,50),(100,60)],colors=['#777777']*3)
        self.action={'dx':25,'dy':0}
    def assess(self,after,motion=None,scene=None,action=None,before=None):
        return assess_response(self.image if before is None else before,after,self.scene,scene or self.scene,action or self.action,motion)
    def test_measured_motion_prevents_false_alarm_on_similar_colors(self):
        motion={'matrix':[[1,0,2],[0,1,0]]}
        self.assertEqual(self.assess(self.image.copy(),motion).state,'changed')
    def test_sparse_pixels_count_even_when_whole_board_mean_is_small(self):
        after=self.image.copy();after[90:96,30:36]=255
        self.assertLess(np.mean(np.abs(after.astype(float)-self.image)),1.5)
        self.assertEqual(self.assess(after).state,'changed')
    def test_known_color_change_counts_but_ocr_missing_does_not(self):
        changed=SimpleNamespace(colors=['#888888','#777777','#777777'])
        missing=SimpleNamespace(colors=[None]*3)
        self.assertEqual(self.assess(self.image.copy(),scene=changed).state,'changed')
        self.assertEqual(self.assess(self.image.copy(),scene=missing).state,'static')
    def test_uniform_island_and_zoom_limit_are_uncertain_not_failed_input(self):
        flat=np.full_like(self.image,200)
        self.assertEqual(self.assess(flat,before=flat).state,'uncertain')
        self.assertEqual(self.assess(self.image.copy(),action={'wheel':32}).state,'uncertain')
    def test_small_corrections_never_count_as_failure(self):
        self.assertEqual(self.assess(self.image.copy(),action={'dx':1,'dy':0}).state,'small')
    def test_failure_requires_four_attempts_multiple_directions_and_time(self):
        guard=ResponseGuard();static=Response('static','test')
        self.assertFalse(guard.observe(static,self.action,0))
        self.assertFalse(guard.observe(static,self.action,1))
        self.assertFalse(guard.observe(static,self.action,2))
        self.assertFalse(guard.observe(static,self.action,3))
        self.assertTrue(guard.observe(static,{'dx':-25,'dy':0},4))
    def test_actual_response_resets_suspicion(self):
        guard=ResponseGuard()
        guard.observe(Response('static','test'),self.action,0)
        guard.observe(Response('changed','delayed frame'),self.action,1)
        self.assertEqual(guard.failures,0)
        self.assertFalse(guard.observe(Response('static','test'),{'dx':-25,'dy':0},3))
    def test_uncertainty_does_not_increment_failure(self):
        guard=ResponseGuard()
        for i in range(20):self.assertFalse(guard.observe(Response('uncertain','flat'),self.action,i))
        self.assertEqual(guard.failures,0)

    def test_delayed_game_frame_is_adopted_without_reporting_input_failure(self):
        import tempfile
        from unittest.mock import MagicMock,patch
        from engine import Runner
        from vision import Scene
        from platform_win import Interrupted
        game=MagicMock();game.hwnd=1;game.captured_at=None
        game.capture_waiting.return_value=self.image
        game.capture.side_effect=[self.image.copy(),self.image.copy(),255-self.image,Interrupted('end test')]
        scene=Scene([],self.scene.markers,self.scene.board,['#777777']*3,110,None)
        rules=[dict(enabled=True,colors=['#FFFFFF'],exact=True,tolerance=0)]+[dict(enabled=False)]*2
        events=[]
        with tempfile.TemporaryDirectory() as folder,patch('engine.Game',return_value=game),patch('engine.configure_ocr'),patch('platform_win.u.GetDpiForWindow',return_value=96),patch('engine.recognize',return_value=scene),patch('engine.candidate_shift',return_value=None),patch('engine.measure_board_motion',return_value=None),patch('engine.time.sleep'):
            runner=Runner(lambda k,d:events.append((k,d)),folder)
            with patch.object(runner.stop,'wait',return_value=False):runner.launch(rules)
        self.assertTrue(any(k=='input_recheck' for k,d in events))
        self.assertTrue(any(k=='action' and d['input_response']=='changed' for k,d in events))
        self.assertFalse(any(k=='error' for k,d in events),events)
        game.click.assert_not_called()
