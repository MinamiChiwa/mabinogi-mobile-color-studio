import unittest
import contextlib
import io
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock,patch
import numpy as np
from point_sampling_probe import choose_probe_target,checked_probe_motion,run_point_probe
from analyze_live_atlas import frame_sequence


def motion(dx=0,dy=0,scale=1):
    return dict(scale=scale,angle=0,matrix=[[scale,0,dx],[0,scale,dy]],inliers=100)


class PointProbeTests(unittest.TestCase):
    def setUp(self):
        self.scene=SimpleNamespace(board=(20,20,320,320),markers=[(70,150),(170,100),(270,200)])
        self.image=np.zeros((360,360,3),np.uint8)

    def test_target_requires_visible_color_variation_away_from_ui(self):
        with self.assertRaisesRegex(RuntimeError,'细色带'):
            choose_probe_target(self.image,self.scene)
        self.image[65:130,190:195]=255
        target=choose_probe_target(self.image,self.scene)
        x,y=target['point']
        self.assertTrue(180<x<210);self.assertGreater(target['gradient'],12)
        self.assertGreater(np.linalg.norm(np.array([x,y])-self.scene.markers[1]),22)

    def test_no_motion_scale_change_and_large_motion_are_rejected(self):
        for m in (None,motion(),motion(.2,0,1.01),motion(2,0),motion(float('nan'),0)):
            with self.subTest(m=m),self.assertRaises(RuntimeError):
                checked_probe_motion(m,small_step=True)
        np.testing.assert_allclose(checked_probe_motion(motion(.24,0),True),[.24,0])

    def test_failed_pair_stops_without_retry_or_dye_click(self):
        game=MagicMock();game.initial=(0,0,360,360);snap=MagicMock(return_value=self.image)
        with patch('point_sampling_probe.choose_probe_target',return_value=dict(point=[190,100],region=2,gradient=50)), \
             patch('point_sampling_probe.measure_board_motion',side_effect=[motion(-20,0),motion()]):
            with self.assertRaisesRegex(RuntimeError,'实际位移'):
                run_point_probe(game,self.scene,self.image,snap,MagicMock())
        self.assertEqual(game.drag.call_count,1);self.assertEqual(game.wheel.call_count,2)
        self.assertEqual(snap.call_count,2);game.click.assert_not_called();game.escape.assert_not_called()

    def test_guard_failure_prevents_second_half_of_pair(self):
        game=MagicMock();game.initial=(0,0,360,360)
        def stop_on_wheel(*args,**kwargs):game.check.side_effect=RuntimeError('stopped')
        game.wheel.side_effect=stop_on_wheel
        with patch('point_sampling_probe.choose_probe_target',return_value=dict(point=[190,100],region=2,gradient=50)), \
             patch('point_sampling_probe.measure_board_motion',return_value=motion(-20,0)):
            with self.assertRaisesRegex(RuntimeError,'stopped'):
                run_point_probe(game,self.scene,self.image,lambda *args:self.image,MagicMock())
        self.assertEqual(game.wheel.call_count,1)

    def test_completed_probe_is_bounded_and_not_an_atlas_capture(self):
        game=MagicMock();game.initial=(0,0,360,360);snap=MagicMock(return_value=self.image);log=MagicMock()
        with patch('point_sampling_probe.choose_probe_target',return_value=dict(point=[190,100],region=2,gradient=50)), \
             patch('point_sampling_probe.measure_board_motion',side_effect=[motion(-20,0)]+[motion(.24,0)]*8+[motion(0,.24)]*8):
            run_point_probe(game,self.scene,self.image,snap,log)
        self.assertEqual(game.wheel.call_count,32);self.assertEqual(game.drag.call_count,1)
        self.assertEqual(snap.call_count,17);game.click.assert_not_called()
        with self.assertRaisesRegex(ValueError,'not atlas'):
            frame_sequence([dict(kind='point_probe_plan')])

    def test_capture_entry_uses_strict_ocr_and_probe_budget_without_grid_drags(self):
        from live_atlas_capture import acquire
        game=MagicMock();game.initial=(0,0,360,360)
        game.geometry.return_value=game.initial
        game.capture.return_value=game.capture_waiting.return_value=self.image
        stop=MagicMock();stop.is_set.return_value=False;stop.wait.return_value=False
        self.scene.cards=[];self.scene.seconds=119
        with tempfile.TemporaryDirectory() as folder, \
             patch('live_atlas_capture.CaptureGame',return_value=game), \
             patch('live_atlas_capture.configure_ocr') as configure, \
             patch('live_atlas_capture.time.monotonic',return_value=100.), \
             patch('live_atlas_capture.u.GetAsyncKeyState',return_value=0), \
             patch('live_atlas_capture.recognize',return_value=self.scene), \
             patch('live_atlas_capture.measure_board_motion',return_value={'scale':1.02}), \
             patch('point_sampling_probe.run_point_probe',return_value=self.image) as probe, \
             contextlib.redirect_stdout(io.StringIO()):
            target=Path(folder)/'capture'
            artifact=acquire(target,strategy='probe',stop=stop)
            records=json.loads((target/'log.json').read_text())
        configure.assert_called_once_with(strict=True);probe.assert_called_once()
        self.assertIs(artifact['scene'],self.scene);self.assertEqual(artifact['deadline'],125.)
        self.assertEqual(artifact['game_deadline'],219.)
        self.assertEqual(artifact['workflow_deadline'],160.)
        self.assertEqual(game.until,219.)
        self.assertEqual(game.stage_until,125.)
        self.assertEqual(records[-1]['strategy'],'probe')
        game.drag.assert_not_called();game.click.assert_not_called()
        self.assertEqual([c.args[0] for c in game.send.call_args_list],[4,16])

    def test_probe_ocr_failure_never_sends_input(self):
        from live_atlas_capture import acquire
        game=MagicMock()
        with tempfile.TemporaryDirectory() as folder, \
             patch('live_atlas_capture.CaptureGame',return_value=game), \
             patch('live_atlas_capture.configure_ocr',side_effect=RuntimeError('missing OCR')):
            with self.assertRaisesRegex(RuntimeError,'missing OCR'):
                acquire(Path(folder)/'capture',strategy='probe')
        self.assertEqual(game.method_calls,[])


if __name__=='__main__':unittest.main()
