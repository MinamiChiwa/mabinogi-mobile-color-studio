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
                                zoom_sampling_steps, summarize_zoom_calibration,
                                _choose_countdown_observation,wait_for_dye_board)
from platform_win import Interrupted,u
from window_target import WindowUnavailable, MultipleWindows


class CaptureGuardTests(unittest.TestCase):
    def test_countdown_observation_rejects_short_ocr_conflict(self):
        """A clipped recheck must not turn a full 119-second timer into 41."""
        anchor=SimpleNamespace(seconds=119)
        clipped=SimpleNamespace(seconds=41)
        selected=_choose_countdown_observation([
            (anchor,10.,None,{'fill_end':679}),
            (clipped,10.4,None,{'fill_end':678}),
        ])
        self.assertIs(selected[0],anchor)

    def test_countdown_observation_follows_elapsed_monotonic_readings(self):
        anchor=SimpleNamespace(seconds=119)
        near=SimpleNamespace(seconds=117)
        selected=_choose_countdown_observation([
            (anchor,10.,None,{'fill_end':679}),
            (near,12.,None,{'fill_end':670}),
        ])
        self.assertIs(selected[0],near)

    def test_countdown_observation_ignores_bar_endpoint_increase(self):
        anchor=SimpleNamespace(seconds=119)
        same=SimpleNamespace(seconds=119)
        selected=_choose_countdown_observation([
            (anchor,10.,None,{'fill_end':600}),
            (same,10.5,None,{'fill_end':650}),
        ])
        # The timer cannot gain time while the bar grows.  Keep the anchor
        # even when OCR values tie.
        self.assertIs(selected[0],anchor)

    def test_countdown_observation_recovers_clipped_first_digit(self):
        """A first-frame 19 must not establish an early deadline when 119 follows."""
        clipped=SimpleNamespace(seconds=19)
        full1=SimpleNamespace(seconds=119)
        full2=SimpleNamespace(seconds=118)
        selected=_choose_countdown_observation([
            (clipped,10.,None,{'fill_end':679}),
            (full1,10.3,None,{'fill_end':678}),
            (full2,11.2,None,{'fill_end':670}),
        ])
        self.assertGreaterEqual(selected[0].seconds,118)

    def test_countdown_observation_does_not_promote_single_spurious_large_reading(self):
        clipped=SimpleNamespace(seconds=19)
        spurious=SimpleNamespace(seconds=119)
        selected=_choose_countdown_observation([
            (clipped,10.,None,{'fill_end':679}),
            (spurious,10.3,None,{'fill_end':678}),
        ])
        # One high reading is insufficient to replace a clipped first frame;
        # wait for an independent confirming frame with a stable bar.
        self.assertIs(selected[0],clipped)

    def test_countdown_observation_requires_bar_and_two_full_frames(self):
        clipped=SimpleNamespace(seconds=19)
        full1=SimpleNamespace(seconds=119)
        full2=SimpleNamespace(seconds=118)
        rows=[(clipped,10.,None,{'fill_end':679}),
              (full1,10.3,None,{'fill_end':678}),
              (full2,11.2,None,{'fill_end':670})]
        selected=_choose_countdown_observation(rows)
        self.assertIs(selected[0],full2)
        # Removing the bar evidence must preserve the conservative short
        # deadline even though the OCR sequence appears plausible.
        no_bar=[(scene,at,frame,None) for scene,at,frame,_bar in rows]
        self.assertIs(_choose_countdown_observation(no_bar)[0],clipped)

    def test_countdown_correction_rejects_growing_bar_or_implausible_time(self):
        clipped=SimpleNamespace(seconds=19)
        rows=[(clipped,10.,None,{'fill_end':679}),
              (SimpleNamespace(seconds=119),10.3,None,{'fill_end':678}),
              (SimpleNamespace(seconds=118),11.2,None,{'fill_end':685})]
        self.assertIs(_choose_countdown_observation(rows)[0],clipped)
        rows[-1]=(SimpleNamespace(seconds=100),11.2,None,{'fill_end':670})
        self.assertIs(_choose_countdown_observation(rows)[0],clipped)
        rows[-1]=(SimpleNamespace(seconds=119),10.3,None,{'fill_end':678})
        self.assertIs(_choose_countdown_observation(rows)[0],clipped)

    def _wait_timer_result(self,readings,bar_ends=None):
        clock=[0.]
        class Stop:
            def is_set(self):return False
            def set(self):pass
            def wait(self,seconds):clock[0]+=seconds;return False
        image=np.zeros((100,100,3),np.uint8)
        scene=lambda value:SimpleNamespace(seconds=value,board=(10,10,90,90),
            markers=[(20,50),(50,50),(80,50)],cards=[])
        scenes=[scene(value) for value in readings]
        game=SimpleNamespace(capture_waiting=lambda:image,capture=lambda:image,
            check=MagicMock(),wheel=MagicMock(),drag=MagicMock(),rotate=MagicMock(),
            click=MagicMock(),until=float('inf'),stage_until=float('inf'))
        signals=[{'fill_end':end} if end is not None else None
                 for end in (bar_ends or [679-i for i in range(len(scenes))])]
        events=[]
        with patch('live_atlas_capture.time.monotonic',side_effect=lambda:clock[0]), \
             patch('live_atlas_capture.recognize',side_effect=scenes) as recognize, \
             patch('live_atlas_capture.timer_bar_signal',side_effect=signals), \
             patch.object(u,'GetAsyncKeyState',return_value=0):
            result=wait_for_dye_board(game,Stop(),started=0.,
                log=lambda kind,**data:events.append((kind,data)))
        for method in (game.wheel,game.drag,game.rotate,game.click):method.assert_not_called()
        return result,game,events,recognize.call_count

    def test_entry_replaces_clipped_deadline_after_two_independent_full_readings(self):
        result,game,events,count=self._wait_timer_result([19,119,118])
        self.assertEqual(count,3)
        self.assertAlmostEqual(result['game_deadline'],118.75)
        self.assertEqual(game.until,result['budget'].deadline)
        self.assertEqual(result['scene'].seconds,118)
        timer=next(data for kind,data in events if kind=='timer')
        self.assertEqual(timer['source'],'corrected_clipped_first_frame')

    def test_entry_single_high_reading_does_not_extend_deadline(self):
        result,_game,events,count=self._wait_timer_result([19,119,None,None,None])
        self.assertEqual(count,5)
        self.assertAlmostEqual(result['game_deadline'],19.25)
        self.assertEqual(result['scene'].seconds,19)
        timer=next(data for kind,data in events if kind=='timer')
        self.assertNotEqual(timer['source'],'corrected_clipped_first_frame')

    def test_entry_bar_growth_or_missing_evidence_preserves_short_deadline(self):
        for ends in ([679,678,685,684,683],[None]*5):
            with self.subTest(ends=ends):
                result,_game,_events,count=self._wait_timer_result([19,119,118,118,118],ends)
                self.assertEqual(count,5)
                self.assertAlmostEqual(result['game_deadline'],19.25)

    def test_normal_short_countdown_does_not_require_extra_rechecks(self):
        result,_game,_events,count=self._wait_timer_result([19,18])
        self.assertEqual(count,2)
        self.assertLessEqual(result['game_deadline'],19.25)

    def test_zoom_calibration_uses_direct_one_notch_measurements(self):
        measurements=[
            dict(steps=-1, direction='down', motion={
                'scale':.9901, 'angle':.01,
                'matrix':[[.9901,0.,-2.],[0.,.9901,-3.]]}),
            dict(steps=1, direction='up', motion={
                'scale':1.0098, 'angle':-.01,
                'matrix':[[1.0098,0.,2.],[0.,1.0098,3.]]}),
        ]
        result=summarize_zoom_calibration(measurements, current_scale=1.2)
        self.assertTrue(result['passed'])
        self.assertAlmostEqual(result['down_log_step'],abs(np.log(.9901)))
        self.assertAlmostEqual(result['up_log_step'],abs(np.log(1.0098)))
        self.assertAlmostEqual(result['current_scale'],1.2*.9901*1.0098)
        self.assertEqual(result['measurements'][0]['motion']['matrix'],
                         measurements[0]['motion']['matrix'])

    def test_zoom_calibration_rejects_missing_direction_without_raising(self):
        result=summarize_zoom_calibration(
            [dict(steps=-1, motion=None), dict(steps=1, motion={'scale':1.01})],
            current_scale=1.2)
        self.assertFalse(result['passed'])
        self.assertIsNone(result['down_log_step'])

    def test_response_diagnostic_uses_manual_entry_without_starting_grid_or_clicking(self):
        image=np.zeros((960,1280,3),np.uint8)
        scene=SimpleNamespace(board=(100,300,600,800),markers=[(180,450),(350,650),(510,500)],
                              cards=[],seconds=120)
        game=SimpleNamespace(initial=(0,0,1280,960),hwnd=123,until=float('inf'),
            geometry=lambda:(0,0,1280,960),capture=lambda:image,capture_waiting=lambda:image,
            check=MagicMock(),pause=MagicMock(),click=MagicMock(),wheel=MagicMock(),
            drag=MagicMock(),move_to=MagicMock(),send=MagicMock())
        outcome=dict(status='complete',completed=1,response_model_installed=False)
        with tempfile.TemporaryDirectory() as tmp, \
             patch('live_atlas_capture.CaptureGame',return_value=game), \
             patch('live_atlas_capture.configure_ocr'), \
             patch('live_atlas_capture.recognize',return_value=scene), \
             patch('live_atlas_capture.measure_board_motion',return_value={'scale':1.02}), \
             patch('live_atlas_capture.CaptureWorker') as worker, \
             patch('live_atlas_capture.grid_scan_plan') as grid, \
             patch('gesture_response_probe.run_response_probe',return_value=(image,outcome)) as probe, \
             patch.object(u,'GetDpiForWindow',return_value=144), \
             contextlib.redirect_stdout(io.StringIO()):
            artifact=acquire(Path(tmp)/'capture',strategy='response',stop=threading.Event())
            records=json.loads((Path(tmp)/'capture/log.json').read_text(encoding='utf8'))
        self.assertIs(artifact['outcome'],outcome)
        self.assertEqual(game.response_probe_dpi,144)
        self.assertEqual(probe.call_count,1)
        self.assertEqual(records[-1]['strategy'],'response')
        worker.assert_not_called();grid.assert_not_called()
        game.click.assert_not_called();game.drag.assert_not_called()
        self.assertEqual([call.args[0] for call in game.send.call_args_list],[4,16])

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
        self.assertEqual(clock.now,303.0)
        self.assertEqual(recognize.call_count,6)
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
                 patch('live_atlas_capture.recognize',return_value=scene) as recognize, \
                 patch('live_atlas_capture.measure_board_motion',return_value={'scale':1.02}), \
                 contextlib.redirect_stdout(io.StringIO()):
                with patch('live_atlas_capture.configure_ocr'):
                    artifact=acquire(folder,None,strategy='grid',stop=threading.Event())

            self.assertTrue((folder/'log.json').is_file())
            records=json.loads((folder/'log.json').read_text())
            timer=next(row for row in records if row['kind']=='timer')
            for call in recognize.call_args_list:
                if call.kwargs['with_ocr']:
                    self.assertFalse(call.kwargs['read_colors'])
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
        scan_frames=[row for row in records if row['kind']=='frame' and row['name'].startswith('grid_')]
        self.assertEqual(len(scan_frames),48)
        self.assertTrue(all(row['scan_timing']['selected']=='baseline' for row in scan_frames))
        self.assertTrue(all(not row.get('settling_probe_files') for row in scan_frames))
        self.assertTrue(all(not row['scan_timing']['probe_times'] for row in scan_frames))
        self.assertEqual(sum(row['kind']=='command' for row in records),48)
        summary=next(row for row in records if row['kind']=='scan_settling_summary')
        self.assertEqual(summary['mode'],'baseline')
        self.assertEqual(summary['potential_saving_seconds'],0)  # static fake board
        self.assertEqual(timer['effective_deadline_elapsed_seconds'],
                         timer['sampling_deadline_elapsed_seconds'])
        zoom=next(row for row in records if row['kind']=='sampling_zoom')
        self.assertEqual(zoom['stop_reason'],'step_limit')
        self.assertFalse(zoom['game_limit_observed'])
        self.assertEqual([call[1] for call in calls if call[0]=='wheel'],[4]*12+[-1,1])
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
        self.assertEqual(recognize.call_count,4)
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
        self.assertEqual(recognize.call_count,2)
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
