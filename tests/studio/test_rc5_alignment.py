"""Regression contracts for native IO, timer jitter and production recovery."""
import copy,tempfile,threading,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
import numpy as np


class TimerAlignmentTests(unittest.TestCase):
    def test_compute_thread_start_failure_releases_the_shared_slot(self):
        import screenshot_compute
        try:
            with patch('screenshot_compute.threading.Thread.start',side_effect=RuntimeError('thread unavailable')):
                with self.assertRaises(RuntimeError):screenshot_compute.cooperative_compute(lambda:1)
            available=screenshot_compute._slot.acquire(blocking=False)
            self.assertTrue(available)
            if available:screenshot_compute._slot.release()
        finally:
            if not available:screenshot_compute._slot.release()
    def test_confirmed_deadline_cannot_extend_from_a_stale_timer(self):
        from screenshot_control import Budget
        budget=Budget(120,.5,now=100)
        budget.observe(20,.083333,now=150);budget.observe(19,.079167,now=151)
        self.assertAlmostEqual(budget.deadline,170)
        budget.observe(19,.079167,now=157)
        self.assertAlmostEqual(budget.deadline,170)

    def test_pending_deadline_cannot_send_an_unconfirmed_optional_gesture(self):
        from screenshot_control import Controller,Budget,TimeEnded
        scene=SimpleNamespace(board=(0,0,100,100),cards=[(0,0,10,10),(20,0,10,10)],markers=[])
        with tempfile.TemporaryDirectory() as folder,patch('screenshot_control.time.monotonic',return_value=205.05):
            owner=SimpleNamespace(stop=threading.Event(),consume_retry_request=lambda:False,folder=Path(folder),event=lambda *a,**k:None)
            budget=Budget(120,.5,now=100);budget.observe(3,.0125,now=205)
            game=Mock();game.capture.return_value=np.zeros((100,100,3),np.uint8)
            c=Controller(owner,game,scene,[],budget);c.check=lambda:None;c.frame=game.capture.return_value
            c.last_timer=205.;perform=Mock()
            with patch('screenshot_control.recognize',return_value=scene), \
                 patch('screenshot_control.read_timer',return_value=None) as read:
                with self.assertRaises(TimeEnded):c.act('pending',perform)
            perform.assert_not_called();self.assertGreaterEqual(read.call_count,1)

    def test_positive_binding_change_cannot_become_a_transient_capture_error(self):
        from screenshot_control import Controller,Budget,PaletteEnded
        scene=SimpleNamespace(board=(0,0,100,100),cards=[(0,0,10,10),(20,0,10,10)],markers=[])
        changed=SimpleNamespace(cards=[(0,0,10,10)])
        with tempfile.TemporaryDirectory() as folder:
            owner=SimpleNamespace(stop=threading.Event(),folder=Path(folder),event=lambda *a,**k:None)
            game=Mock();game.capture.return_value=np.zeros((100,100,3),np.uint8)
            c=Controller(owner,game,scene,[],Budget(120,.5));c.check=lambda:None
            with patch('screenshot_control.recognize',side_effect=[changed,ValueError('flash'),ValueError('flash')]):
                with self.assertRaises(PaletteEnded) as exc:c.capture('changed')
            self.assertFalse(exc.exception.recoverable)
    def test_slow_index_build_yields_to_stop_before_it_finishes(self):
        from screenshot_compute import cooperative_compute
        entered=threading.Event();finish=threading.Event()
        def expensive():entered.set();finish.wait(2);return 1
        def check():
            if entered.is_set():raise InterruptedError('stop compute')
        started=time.monotonic()
        try:
            with self.assertRaises(InterruptedError):cooperative_compute(expensive,check)
            self.assertLess(time.monotonic()-started,.5)
        finally:finish.set()
    def test_first_sudden_drop_requires_a_second_temporal_confirmation(self):
        from screenshot_control import Budget
        budget=Budget(120,.5,now=100)
        self.assertEqual(budget.observe(3,.0125,now=205),'awaiting_time_agreement')
        self.assertEqual(budget.remaining(205),15)
        self.assertEqual(budget.observe(2,.00833,now=206),'text_and_bar_agree')
        self.assertEqual(budget.remaining(206),2)

    def test_no_timer_or_bar_does_not_create_a_fresh_120_second_session(self):
        from screenshot_control import Budget
        budget=Budget(None,None,now=100)
        self.assertLessEqual(budget.remaining(100),90)
        self.assertTrue(budget.initial_uncertain)


class NativeAlignmentTests(unittest.TestCase):
    def test_f9_during_timeout_return_keeps_the_terminal_stop_reason(self):
        from test_native_frame_budget_recovery import ControllerFrameBudgetRecoveryTests
        from test_native_live_controller import FixtureIO
        io=FixtureIO();original=io.input_backend;checks=0;check=io.check
        def backend(deadline):
            if io.actions:raise TimeoutError('phase timeout')
            return original(deadline)
        def stopped(deadline):
            nonlocal checks
            if io.actions:
                checks+=1
                if checks>1:raise InterruptedError('F9')
            return check(deadline)
        io.input_backend=backend;io.check=stopped
        result=ControllerFrameBudgetRecoveryTests().run_io(io)
        self.assertEqual(result['stop_reason'],'interrupted')
        self.assertIn('F9',result['error']);self.assertEqual(len(io.actions),1)
    def test_single_inactive_native_read_is_confirmed_before_ending(self):
        from native_live.project_probe_io import ProjectProbeIO
        from native_live.session_status import PaletteEnded
        io=object.__new__(ProjectProbeIO);io.reference=dict(instance_address=123,baseline=dict(
            active=True,process_identity=[1],session_token=['same']))
        io.backend=Mock();io.backend.process_identity.return_value=[1]
        io.backend.probe.return_value=dict(active=True,process_identity=[1],session_token=['same'])
        io._input_guard=lambda:None;io.deadline=time.monotonic()+10
        row=io._check_observed_session(dict(active=False),'probe')
        self.assertTrue(row['active']);io.backend.probe.assert_called_once()

    def test_native_real_closure_stays_terminal_after_repeated_reads(self):
        from native_live.project_probe_io import ProjectProbeIO
        from native_live.session_status import PaletteEnded
        io=object.__new__(ProjectProbeIO);io.reference=dict(instance_address=123,baseline=dict(
            active=True,process_identity=[1],session_token=['same']))
        io.backend=Mock();io.backend.process_identity.return_value=[1];io.backend.probe.return_value=dict(active=False)
        io._input_guard=lambda:None;io.deadline=time.monotonic()+10
        def stop(kind,*args,**kwargs):raise kind('closed',{})
        io._session_stop=stop
        with self.assertRaises(PaletteEnded) as exc:io._check_observed_session(dict(active=False),'probe')
        self.assertFalse(exc.exception.recoverable);self.assertEqual(io.backend.probe.call_count,2)

    def test_native_phase_timeout_restores_independently_measured_anchor(self):
        from test_native_frame_budget_recovery import ControllerFrameBudgetRecoveryTests
        from test_native_live_controller import FixtureIO
        io=FixtureIO();runner=ControllerFrameBudgetRecoveryTests();start=copy.deepcopy(io.pose)
        original=io.input_backend;failed=[]
        from native_palette_scoring import score_native_pose
        from native_live.compromise import observed_quality
        initial_quality=observed_quality(io.checkpoint('initial_fixture',90)['client_hex'],io.case['rules'])
        perform=io.perform_candidate;shifted=[]
        def drift(record,label,deadline):
            receipt=perform(record,label,deadline)
            if not shifted:
                width=io.geometry.board[2]-io.geometry.board[0]
                for pixels in (-120,-100,-80,-50,-30,10,30,50,80,120):
                    pose=copy.deepcopy(start);pose['position'][0]+=pixels/width
                    if observed_quality(score_native_pose(io.session,pose,io.case['rules'])['colors'],io.case['rules'])>initial_quality:
                        io.pose=pose;shifted.append(True);break
            return receipt
        io.perform_candidate=drift
        def backend(deadline):
            if io.actions and not failed:
                failed.append(True);raise TimeoutError('Recoverable preparation phase timeout')
            return original(deadline)
        io.input_backend=backend
        result=runner.run_io(io)
        self.assertTrue(result.get('failure_recovery',{}).get('verified'),result.get('error'))
        self.assertTrue(result['best_current'])
        self.assertTrue(result['screenshot_verified'])
        self.assertLess(io.t,result['effective_deadline'])
        self.assertTrue(shifted)
        self.assertTrue(any(step['purpose']=='restore_best' for step in result['steps']))

    def test_native_terminal_stops_never_authorize_return_input(self):
        from test_native_frame_budget_recovery import ControllerFrameBudgetRecoveryTests
        from test_native_live_controller import FixtureIO
        from native_live.session_status import PaletteEnded,SessionBindingChanged
        for kind in (InterruptedError,PaletteEnded,SessionBindingChanged):
            with self.subTest(kind=kind):
                io=FixtureIO();original=io.input_backend
                def stopped(deadline):
                    if io.actions:
                        if kind is InterruptedError:raise InterruptedError('F9')
                        raise kind('terminal',{})
                    return original(deadline)
                io.input_backend=stopped;result=ControllerFrameBudgetRecoveryTests().run_io(io)
                self.assertEqual(len(io.actions),1)
                self.assertFalse(result.get('failure_recovery',{}).get('attempted',False))

    def test_native_frames_enqueue_png_without_calling_encoder_on_reader(self):
        from native_live.project_probe_io import ProjectProbeIO
        from screenshot_evidence import ScreenshotWriter
        io=object.__new__(ProjectProbeIO);io.check=lambda deadline:None;io._input_guard=lambda:None
        io.last_observation=dict(window_context=dict(window=dict(client_size_physical=[100,80])),
            window_mapping_candidate=dict(client_board_candidate=[0,20,100,80]),region_count=2)
        io.game=SimpleNamespace(capture=lambda:np.zeros((80,100,3),np.uint8))
        io.card_cache={};io.previous_timer=None;io.last_client_hex=None
        io.stop=threading.Event();io.sent_any=False
        decoded=dict(cards=[[5,0,40,10],[55,0,40,10]],hex=['#000000']*2,remaining_seconds=None)
        with tempfile.TemporaryDirectory() as folder:
            io.folder=Path(folder)
            with patch('native_live.project_probe_io.read_probe_frame',return_value=decoded), \
                 patch.object(ScreenshotWriter,'submit') as submit, \
                 patch('PIL.Image.Image.save',side_effect=AssertionError('Synchronous encoding')):
                try:frames=io.frames('test',time.monotonic()+20)
                finally:io.release()
            self.assertEqual(len(frames),2);self.assertEqual(submit.call_count,2)

    def test_same_native_sample_lattice_reuses_whole_rgb_preprocessing(self):
        from native_periodic_search import periodic_samples
        pixels=np.random.default_rng(7).integers(0,256,(254,254,3),dtype=np.uint8)
        pixels.setflags(write=False);session=dict(pixels=(pixels,),color_preserve_ratio=.25)
        first=periodic_samples(session,0,.0,.5)
        with patch('native_periodic_search.sample_cpu',side_effect=AssertionError('Repeated lattice sampling')):
            second=periodic_samples(session,0,.0,.5)
        self.assertIs(first,second)
        self.assertFalse(first[1].flags.writeable)
        changed=pixels.copy();changed[0,0]=0;changed.setflags(write=False);session['pixels']=(changed,)
        self.assertIsNot(first,periodic_samples(session,0,.0,.5))
