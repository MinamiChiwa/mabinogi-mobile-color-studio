import threading
import time
import unittest
import contextlib
import io
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock,patch
import numpy as np
from PIL import Image
from live_atlas_capture import (CaptureGame, acquire, preflight, grid_scan_plan,
                                coverage_fill_positions, sampling_frame_is_safe,
                                zoom_sampling_steps)
from platform_win import Interrupted,u
from window_target import WindowUnavailable, MultipleWindows


class CaptureGuardTests(unittest.TestCase):
    def test_late_manual_entry_and_failed_activation_do_not_abort_waiting(self):
        class Clock:
            now=0.
            def monotonic(self):return self.now
        class Stop:
            def __init__(self,clock):self.clock=clock;self.waits=iter((200.,101.,1.))
            def is_set(self):return False
            def wait(self,timeout):
                try:self.clock.now+=next(self.waits)
                except StopIteration:self.clock.now+=timeout
                return False
        clock=Clock();stop=Stop(clock);image=np.zeros((100,100,3),np.uint8)
        focus=MagicMock(side_effect=RuntimeError('foreground denied'))
        game=SimpleNamespace(
            focus=focus,
            geometry=lambda:(0,0,100,100),capture_waiting=lambda:image,capture=lambda:image,
            check=MagicMock(side_effect=[None,None,None,Interrupted('stop after timer fallback')]))
        scenes=[SimpleNamespace(seconds=None),SimpleNamespace(seconds=None),
                SimpleNamespace(seconds=100,board=(10,10,90,90),markers=[(20,50),(50,50),(80,50)],cards=[])]
        scenes.extend(SimpleNamespace(seconds=None) for _ in range(4))
        events=[]
        with tempfile.TemporaryDirectory() as tmp, \
             patch('live_atlas_capture.CaptureGame',return_value=game), \
             patch('live_atlas_capture.configure_ocr'), \
             patch('live_atlas_capture.time.monotonic',side_effect=clock.monotonic), \
             patch('live_atlas_capture.recognize',side_effect=scenes) as recognize, \
             patch.object(u,'GetAsyncKeyState',return_value=0):
            with self.assertRaisesRegex(Interrupted,'stop after timer fallback'):
                acquire(Path(tmp)/'capture',strategy='grid',stop=stop,activate=True,
                        emit=lambda kind,**data:events.append((kind,data)))
        self.assertEqual(clock.now,302.75)
        self.assertEqual(recognize.call_count,7)
        focus.assert_called_once_with()
        self.assertTrue(any(kind=='activation' for kind,_ in events))

    def test_sampling_zoom_stops_at_game_limit_or_clipped_frame(self):
        self.assertEqual(zoom_sampling_steps([1.02, 1.02, 1.0, 1.08], [True]*4), 2)
        self.assertEqual(zoom_sampling_steps([1.02]*4, [True]*4), 4)
        self.assertEqual(zoom_sampling_steps([1.0], [True]), 0)
        self.assertEqual(zoom_sampling_steps([1.02, 1.04, 1.06], [True, False, True]), 1)

    def test_sampling_geometry_requires_all_markers_inside_board(self):
        scene=type('Scene', (), {'board': (10, 10, 90, 90),
                                 'markers': [(20, 20), (50, 50), (80, 80)]})()
        self.assertTrue(sampling_frame_is_safe(scene, (100, 100, 3)))
        scene.markers[2]=(95, 80)
        self.assertFalse(sampling_frame_is_safe(scene, (100, 100, 3)))

    def test_grid_scan_is_two_dimensional_and_interleaves_holdouts(self):
        plan = grid_scan_plan((0, 0, 500, 500))
        self.assertEqual(len(plan), 48)
        self.assertEqual(sum(p['supplemental'] for p in plan),9)
        self.assertEqual(sum(p['supplemental_kind']=='marker_column_fill' for p in plan),4)
        self.assertEqual(sum(p['supplemental_kind']=='coverage_fill' for p in plan),5)
        self.assertEqual(sum(p['dy'] != 0 for p in plan), 4)
        self.assertGreaterEqual(sum(p['holdout'] for p in plan), 5)
        xs=[];ys=[];x=y=0
        for p in plan:
            x+=p['dx'];y+=p['dy'];xs.append(x);ys.append(y)
        self.assertEqual(max(xs)-min(xs), 700)
        self.assertEqual(max(ys)-min(ys), 800)
        self.assertTrue(all(abs(p['dx']) <= 100 and abs(p['dy']) <= 200 for p in plan))
        self.assertEqual([i+1 for i,p in enumerate(plan) if p['holdout']],
                         [9,16,24,33,39,45])
        self.assertEqual(coverage_fill_positions((0,0,500,500)),[
            dict(x=250,y=0),dict(x=50,y=400),dict(x=125,y=400),
            dict(x=450,y=400),dict(x=650,y=400)])

    def game(self):
        g=CaptureGame.__new__(CaptureGame)
        g.stop=threading.Event();g.until=time.monotonic()+90;g.hwnd=123
        g.initial=(0,40,3839,2049);g.geometry=lambda:g.initial
        return g

    def test_staggered_scan_keeps_drag_count_and_vertical_return_pairs(self):
        plan=grid_scan_plan((0,0,500,500),row_stagger=.05)
        self.assertEqual(len(plan),48)
        pose=np.zeros(2);rows={0:[tuple(pose)]}
        base_rows={0:[tuple(pose)]}
        for step in plan:
            self.assertLessEqual(abs(step['dx']),100)
            self.assertLessEqual(abs(step['dy']),200)
            pose += [step['dx'],step['dy']]
            rows.setdefault(step['row'],[]).append(tuple(pose))
            if not step['supplemental']:
                base_rows.setdefault(step['row'],[]).append(tuple(pose))
        self.assertEqual(sorted(p[0] for p in base_rows[0]),sorted(p[0] for p in base_rows[2]))
        self.assertEqual(sorted(p[0] for p in base_rows[0]),sorted(p[0] for p in base_rows[4]))
        self.assertEqual(min(p[0] for p in base_rows[1]),25)
        self.assertEqual(min(p[0] for p in base_rows[3]),-25)
        self.assertEqual(sum(p['holdout'] for p in plan),6)
        with self.assertRaises(ValueError):grid_scan_plan((0,0,500,500),row_stagger=float('nan'))

    def test_supplemental_moves_preserve_the_original_holdout_positions(self):
        board=(0,0,500,500)

        def holdout_positions(plan):
            x=y=0;positions=[]
            for step in plan:
                x+=step['dx'];y+=step['dy']
                if step['holdout']:positions.append((x,y))
            return positions

        original=grid_scan_plan(board,row_stagger=.05,marker_column_fill=False,
                                coverage_fill=False)
        supplemented=grid_scan_plan(board,row_stagger=.05,marker_column_fill=True,
                                    coverage_fill=True)
        self.assertEqual(holdout_positions(supplemented),holdout_positions(original))

    def test_f9_sets_stop_before_any_input(self):
        g=self.game()
        with patch.object(u,'GetAsyncKeyState',return_value=-32768):
            with self.assertRaises(Interrupted):g.check()
        self.assertTrue(g.stop.is_set())

    def test_deadline_stops_even_when_game_is_available(self):
        g=self.game();g.until=0
        with patch.object(u,'GetAsyncKeyState',return_value=0):
            with self.assertRaisesRegex(Interrupted,'截止时间'):g.check()

    def test_sampling_stage_reserve_cannot_extend_workflow_deadline(self):
        g=self.game();g.until=160.;g.stage_until=148.
        with patch.object(u,'GetAsyncKeyState',return_value=0), \
             patch.object(u,'GetForegroundWindow',return_value=123), \
             patch('live_atlas_capture.time.monotonic',return_value=149.):
            with self.assertRaises(Interrupted):g.check()
            g.stage_until=float('inf');g.check()
        with patch.object(u,'GetAsyncKeyState',return_value=0), \
             patch('live_atlas_capture.time.monotonic',return_value=160.):
            with self.assertRaises(Interrupted):g.check()

    def test_expiry_at_final_input_boundary_still_allows_button_release(self):
        g=self.game();g.until=100.
        with patch.object(u,'GetAsyncKeyState',return_value=0), \
             patch('live_atlas_capture.time.monotonic',return_value=100.), \
             patch('live_atlas_capture.Game.send') as send:
            for flag in (1,2,8,0x800,0xC001):
                with self.assertRaises(Interrupted):g.send(flag)
            send.assert_not_called()
            g.send(4);g.send(16)
        self.assertEqual([call.args[0] for call in send.call_args_list],[4,16])

    def test_scoped_diagnostic_guard_reaches_final_send_and_unwinds(self):
        g=self.game()
        with patch.object(g,'check'),patch('live_atlas_capture.time.monotonic',return_value=5.), \
             patch('live_atlas_capture.Game.send') as send:
            def stopped():raise Interrupted('diagnostic stopped')
            with self.assertRaisesRegex(Interrupted,'diagnostic stopped'):
                with g.input_scope(10.,stopped):g.send(0x800,data=120)
            send.assert_not_called()
            self.assertEqual(g._input_scopes,[])
            with g.input_scope(4.,lambda:None):
                with self.assertRaises(Interrupted):g.send(0x800,data=120)
                g.send(4);g.send(16)
            self.assertEqual([call.args[0] for call in send.call_args_list],[4,16])

    def test_scoped_guard_delay_cannot_cross_deadline_at_input_boundary(self):
        g=self.game();now=[5.]
        with patch.object(g,'check'),patch('live_atlas_capture.time.monotonic',side_effect=lambda:now[0]), \
             patch('live_atlas_capture.Game.send') as send:
            def slow():now[0]=10.
            with g.input_scope(10.,slow),self.assertRaises(Interrupted):g.send(0x800,data=120)
            send.assert_not_called()

    def test_manual_wait_does_not_start_sampling_clock(self):
        with patch('live_atlas_capture.Game.__init__',return_value=None):
            g=CaptureGame(threading.Event())
        g.stop=threading.Event();g.hwnd=123;g.initial=(0,0,1280,960)
        g.geometry=lambda:g.initial
        with patch('live_atlas_capture.time.monotonic',return_value=10000), \
             patch.object(u,'GetAsyncKeyState',return_value=0), \
             patch.object(u,'GetForegroundWindow',return_value=123):
            g.check()
            g.until=9999
            with self.assertRaises(Interrupted):g.check()

    def test_focus_and_geometry_changes_stop_capture(self):
        g=self.game()
        with patch.object(u,'GetAsyncKeyState',return_value=0),patch.object(u,'GetForegroundWindow',return_value=0):
            with self.assertRaises(Interrupted):g.check()
        g.geometry=lambda:(0,40,1280,960)
        with patch.object(u,'GetAsyncKeyState',return_value=0),patch.object(u,'GetForegroundWindow',return_value=123):
            with self.assertRaises(Interrupted):g.check()

    def test_grid_capture_returns_builder_artifact_and_only_releases_buttons(self):
        clock=[100.]
        scene=SimpleNamespace(board=(10,10,90,90),markers=[(20,50),(50,50),(80,50)],
                              cards=[],seconds=120)
        calls=[]

        class FakeGame:
            def __init__(self,stop,target=None):
                self.stop=stop;self.initial=(0,0,100,100);self.until=clock[0]+90
            def geometry(self):return self.initial
            def capture(self):
                calls.append(('capture',))
                return np.zeros((100,100,3),dtype=np.uint8)
            def capture_waiting(self):return self.capture()
            def check(self):pass
            def pause(self,seconds):clock[0]+=seconds
            def click(self,point):calls.append(('click',point))
            def wheel(self,board,steps):calls.append(('wheel',steps))
            def drag(self,board,dx,dy):calls.append(('drag',dx,dy))
            def move_to(self,point):calls.append(('move_to',point))
            def send(self,flag):calls.append(('send',flag))

        def monotonic():
            clock[0]+=.001
            return clock[0]

        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'capture'
            with patch('live_atlas_capture.CaptureGame',FakeGame), \
                 patch('live_atlas_capture.time.monotonic',side_effect=monotonic), \
                 patch('live_atlas_capture.recognize',return_value=scene), \
                 patch('live_atlas_capture.measure_board_motion',return_value={'scale':1.02}), \
                 contextlib.redirect_stdout(io.StringIO()):
                with patch('live_atlas_capture.configure_ocr'):
                    artifact=acquire(folder,None,strategy='grid',stop=threading.Event())

            self.assertTrue((folder/'log.json').is_file())
            records=json.loads((folder/'log.json').read_text())
            timer=next(row for row in records if row['kind']=='timer')
            self.assertEqual(timer['seconds'],120)
            self.assertIn('elapsed_seconds',timer)

        self.assertEqual(artifact['folder'],folder)
        self.assertIs(artifact['scene'],scene)
        self.assertEqual(artifact['image'].shape,(100,100,3))
        self.assertEqual(artifact['geometry'],(0,0,100,100))
        self.assertIsNotNone(artifact['deadline'])
        self.assertEqual(artifact['game'].until,artifact['deadline'])
        # The 60-second figure is a performance reference only; the OCR game
        # countdown remains the effective deadline.
        self.assertAlmostEqual(artifact['deadline']-artifact['ready_at'],120.,places=2)
        self.assertEqual(artifact['game_deadline'],artifact['deadline'])
        self.assertEqual(artifact['game'].stage_until,float('inf'))
        self.assertEqual(timer['effective_deadline_elapsed_seconds'],
                         timer['sampling_deadline_elapsed_seconds'])
        zoom=next(row for row in records if row['kind']=='sampling_zoom')
        self.assertEqual(zoom['stop_reason'],'step_limit')
        self.assertFalse(zoom['game_limit_observed'])
        self.assertEqual([call[1] for call in calls if call[0]=='click'],[])
        self.assertEqual([call[1] for call in calls if call[0]=='send'],[4,16])
        first_drag=next(i for i,call in enumerate(calls) if call[0]=='drag')
        prefix=calls[:first_drag]
        last_capture=max(i for i,call in enumerate(prefix) if call[0]=='capture')
        last_move=max(i for i,call in enumerate(prefix) if call[0]=='move_to')
        self.assertEqual(prefix[last_move],('move_to',(50,15)))
        self.assertLess(last_move,last_capture)

    def test_waiting_for_manual_entry_never_clicks(self):
        calls=[]
        class FakeGame:
            def __init__(self,stop,target=None):
                self.initial=(0,0,1280,960);self.stop=stop;self.until=time.monotonic()+90
            def geometry(self):return self.initial
            def focus(self):pass
            def pause(self,seconds):raise RuntimeError('manual wait test')
            def capture(self):calls.append(('capture',));return np.zeros((20,20,3),dtype=np.uint8)
            def capture_waiting(self):self.stop.set();return None
            def click(self,point):calls.append(('click',point))
            def send(self,flag):calls.append(('send',flag))

        with tempfile.TemporaryDirectory() as tmp:
            with patch('live_atlas_capture.CaptureGame',FakeGame), \
                 patch('live_atlas_capture.configure_ocr'), \
                 patch('live_atlas_capture.recognize',side_effect=RuntimeError('not ready')):
                with self.assertRaises(Interrupted):
                    acquire(Path(tmp)/'capture',None,strategy='grid',stop=threading.Event())
        self.assertEqual(calls,[])

    def test_missing_ocr_with_legacy_entry_argument_sends_no_input(self):
        from unittest.mock import MagicMock
        game=MagicMock()
        with tempfile.TemporaryDirectory() as tmp, \
             patch('live_atlas_capture.CaptureGame',return_value=game), \
             patch('live_atlas_capture.configure_ocr',side_effect=RuntimeError('OCR missing')) as configure:
            with self.assertRaisesRegex(RuntimeError,'OCR missing'):
                acquire(Path(tmp)/'capture',entry=(1,2),strategy='grid')
        configure.assert_called_once_with(strict=True)
        self.assertEqual(game.method_calls,[])

    def test_stop_button_while_game_is_unfocused_sends_no_input(self):
        from unittest.mock import MagicMock
        game=MagicMock();stop=threading.Event();stop.set()
        with tempfile.TemporaryDirectory() as tmp, \
             patch('live_atlas_capture.CaptureGame',return_value=game), \
             patch('live_atlas_capture.configure_ocr'), \
             patch.object(u,'GetForegroundWindow',return_value=0), \
             patch.object(u,'GetAsyncKeyState',return_value=0):
            with self.assertRaises(Interrupted):
                acquire(Path(tmp)/'capture',strategy='grid',stop=stop)
        self.assertEqual(game.method_calls,[])

    def test_failed_timer_recheck_never_sends_wheel_or_drag(self):
        from unittest.mock import MagicMock
        game=MagicMock();game.geometry.return_value=(0,0,100,100)
        game.capture.return_value=game.capture_waiting.return_value=np.zeros((100,100,3),np.uint8)
        game.check.side_effect=[None,None,None,Interrupted('stop after timer fallback')]
        scene=SimpleNamespace(board=(10,10,90,90),markers=[(20,50),(50,50),(80,50)],cards=[],seconds=119)
        with tempfile.TemporaryDirectory() as tmp, \
             patch('live_atlas_capture.CaptureGame',return_value=game), \
             patch('live_atlas_capture.configure_ocr'), \
             patch.object(u,'GetAsyncKeyState',return_value=0), \
             patch('live_atlas_capture.recognize',side_effect=[scene]+[SimpleNamespace(seconds=None)]*4) as recognize:
            with self.assertRaisesRegex(Interrupted,'stop after timer fallback'):
                acquire(Path(tmp)/'capture',strategy='grid')
        self.assertEqual(recognize.call_count,5)
        game.send.assert_not_called();game.wheel.assert_not_called();game.drag.assert_not_called()

    def test_transient_timer_ocr_failure_is_retried_before_any_input(self):
        game=MagicMock();game.geometry.return_value=(0,0,100,100)
        game.capture.return_value=game.capture_waiting.return_value=np.zeros((100,100,3),np.uint8)
        game.check.side_effect=[None,Interrupted('stop after timer verification')]
        scene=SimpleNamespace(board=(10,10,90,90),markers=[(20,50),(50,50),(80,50)],cards=[],seconds=119)
        recovered=SimpleNamespace(seconds=117)
        with tempfile.TemporaryDirectory() as tmp, \
             patch('live_atlas_capture.CaptureGame',return_value=game), \
             patch('live_atlas_capture.configure_ocr'), \
             patch.object(u,'GetAsyncKeyState',return_value=0), \
             patch('live_atlas_capture.recognize',side_effect=[scene,SimpleNamespace(seconds=None),recovered]) as recognize:
            with self.assertRaisesRegex(Interrupted,'stop after timer verification'):
                acquire(Path(tmp)/'capture',strategy='grid')
        self.assertEqual(recognize.call_count,3)
        game.send.assert_not_called();game.wheel.assert_not_called();game.drag.assert_not_called()

    def test_auto_window_detection_waits_for_game_to_open_and_f9_cancels(self):
        stop=threading.Event();image=np.zeros((20,20,3),np.uint8);events=[]
        game=SimpleNamespace(manual_target=None,capture_waiting=lambda:(stop.set() or None))
        missing=WindowUnavailable('未找到游戏窗口。请启动游戏，或手动选择窗口。')
        with tempfile.TemporaryDirectory() as tmp, \
             patch('live_atlas_capture.CaptureGame',side_effect=[missing,game]) as construct, \
             patch('live_atlas_capture.configure_ocr'), \
             patch.object(u,'GetAsyncKeyState',return_value=0):
            with self.assertRaises(Interrupted):
                acquire(Path(tmp)/'capture',strategy='grid',stop=stop,
                        emit=lambda kind,**data:events.append((kind,data)))
        self.assertEqual(construct.call_count,2)
        self.assertTrue(any(kind=='waiting' and '未找到游戏窗口' in data['message'] for kind,data in events))

    def test_ambiguous_game_windows_fail_immediately_for_manual_selection(self):
        from pathlib import Path
        stop=threading.Event()
        with tempfile.TemporaryDirectory() as tmp, \
             patch('live_atlas_capture.CaptureGame',side_effect=MultipleWindows('发现多个游戏窗口，请手动选择目标窗口。')) as construct, \
             patch('live_atlas_capture.configure_ocr'), \
             patch.object(u,'GetAsyncKeyState',return_value=0):
            with self.assertRaises(MultipleWindows):
                acquire(Path(tmp)/'capture',strategy='grid',stop=stop)
        construct.assert_called_once()

    def test_closed_manually_selected_window_is_reported_instead_of_silently_waiting(self):
        target=object();stop=threading.Event()
        game=SimpleNamespace(manual_target=target,capture_waiting=MagicMock(
            side_effect=WindowUnavailable('所选窗口已关闭，请重新选择游戏窗口。')))
        with tempfile.TemporaryDirectory() as tmp, \
             patch('live_atlas_capture.CaptureGame',return_value=game), \
             patch('live_atlas_capture.configure_ocr'), \
             patch.object(u,'GetAsyncKeyState',return_value=0):
            with self.assertRaisesRegex(WindowUnavailable,'所选窗口已关闭'):
                acquire(Path(tmp)/'capture',strategy='grid',stop=stop)

    def test_preflight_reports_missing_ocr_without_input(self):
        g=self.game();g.until=float('inf')
        def make_game(stop):g.stop=stop;return g
        with tempfile.TemporaryDirectory() as tmp, \
             patch('live_atlas_capture.CaptureGame',side_effect=make_game), \
             patch('platform_win.valid_target',return_value=True), \
             patch('live_atlas_capture.configure_ocr',side_effect=RuntimeError('missing English data')), \
             patch('live_atlas_capture.ImageGrab.grab',return_value=Image.new('RGB',(3839,2049))), \
             patch.object(g,'send') as send, patch.object(u,'GetDpiForWindow',return_value=96), \
             contextlib.redirect_stdout(io.StringIO()):
            result=preflight(Path(tmp)/'preflight')
        self.assertFalse(result['passed']);self.assertFalse(result['input_sent'])
        self.assertFalse(result['ocr_available']);self.assertTrue(all(result['guards'].values()))
        self.assertTrue(result['guards']['geometry_guard_simulated'])
        send.assert_not_called()
