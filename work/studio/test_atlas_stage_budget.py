"""Discrete endpoints and stage deadlines with elapsed time and independent input."""
from contextlib import contextmanager
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from atlas_bound_route import bind_candidate
from atlas_execution import CandidateBatch, Context, execute_candidate, reposition_budget
from atlas_runtime import Adapter
from atlas_stage_budget import ExecutionStageBudget, StageBudgetExceeded
from atlas_live_adapter import choice_current
from live_atlas_capture import CaptureGame


class Clock:
    def __init__(self):self.now=0.
    def __call__(self):return self.now
    def advance(self,seconds):self.now+=seconds


class GradientAtlas:
    def sample(self,region,points,offset):
        points=np.asarray(points)
        values=np.column_stack((np.floor(points[:,0]*12).clip(0,255),
                                np.full(len(points),80),np.full(len(points),120)))
        return values,np.ones(len(points),bool)


class TimedGame:
    """Physical drag response is computed from cursor increments, not forecasts."""
    def __init__(self,clock):
        self.clock=clock;self.pose=np.eye(3);self.initial=(0,0,900,900)
        self.sent=[];self.scopes=[];self.stop=False;self.until=20.;self.point_seconds=.1
    def geometry(self):return self.initial
    def check(self):
        if self.stop:raise InterruptedError('F9')
        if self.clock()>=self.until:raise InterruptedError('game deadline')
    def capture(self):self.check();self.clock.advance(.05);return self.pose.copy()
    def pause(self,seconds):self.check();self.clock.advance(seconds);self.check()
    @contextmanager
    def input_scope(self,deadline,guard,*,expiry_factory=None):
        self.scopes.append((deadline,guard,expiry_factory))
        try:yield
        finally:self.scopes.pop()
    def send(self,flags,dx=0,dy=0):
        if flags not in (4,16):
            self.check()
            for deadline,guard,factory in self.scopes:
                if self.clock()>=deadline:raise factory('soft input deadline')
                guard()
        self.sent.append((flags,self.clock()))
        if flags==1:
            self.pose[0,2]+=dx;self.pose[1,2]+=dy
    def perform_gesture(self,gesture):
        self.send(2)
        try:
            for a,b in zip(gesture.points,gesture.points[1:]):
                self.clock.advance(self.point_seconds)
                self.send(1,b[0]-a[0],b[1]-a[1])
        finally:self.send(4)
    def move_to(self,point):self.send(1)


class TimedAdapter(Adapter):
    def __init__(self,game,*,read_seconds=.1,soft_ocr_timeout=False):
        scene=SimpleNamespace(board=(0,0,900,900),markers=((150,400),(450,400),(750,400)))
        super().__init__(game,scene,'test')
        self.recovery_enabled=True;self.reads=0;self.read_seconds=read_seconds
        self.soft_ocr_timeout=soft_ocr_timeout
    def motion(self,before,after):
        self.check_observation();self.g.clock.advance(.05)
        return dict(matrix=(after@np.linalg.inv(before))[:2].tolist(),angle=0.,scale=1.)
    def read_codes(self,image):
        self.check_observation();self.reads+=1
        if self.soft_ocr_timeout:
            self.g.clock.now=self._stage_budget.observation_deadline
            raise StageBudgetExceeded('OCR reached its absolute deadline')
        self.g.clock.advance(self.read_seconds);self.check_observation()
        return ['#112233']*3


class StageBudgetTests(unittest.TestCase):
    rules=[dict(enabled=True,exact=False,colors=['#112233'],tolerance=8)]*3

    def row(self,dx=20,dy=0):
        return dict(id=0,dx=dx,dy=dy,angle=0.,scale=1.,colors=['#112233']*3,deltas=[0]*3)

    def test_diagonal_rounding_retains_a_reachable_endpoint_and_rescores_it(self):
        board=(0,0,100,100);markers=((12,20),(14,40),(16,60))
        proposal=self.row(.49,.49)
        proposal.update(colors=['#FFFFFF']*3,deltas=[0]*3,accepted=True)
        row,budget=bind_candidate(proposal,GradientAtlas(),[0,0],board,markers,self.rules,0,50,
                                  require_stable=True,allow_color_compromise=True)
        self.assertTrue(budget['allowed'])
        self.assertEqual(budget['steps'],0)
        np.testing.assert_allclose(row['matrix'],[[1,0,0],[0,1,0]])
        self.assertNotEqual(row['colors'],proposal['colors'])
        self.assertFalse(row['verified'])
        self.assertEqual(row['prediction_pose_source'],'bound_integer_route_forecast')

    def test_nearest_integer_endpoint_is_scored_instead_of_fractional_proposal(self):
        row,budget=bind_candidate(self.row(20.49,30.49),GradientAtlas(),[0,0],
            (0,0,900,900),((150,400),(450,400),(750,400)),self.rules,0,50)
        self.assertTrue(budget['allowed'])
        np.testing.assert_allclose(row['matrix'],[[1,0,20],[0,1,30]])
        self.assertLess(max(budget['planned_marker_errors']),1.)
        self.assertGreater(max(budget['planned_marker_errors']),.65)

    def execute(self,game,adapter,budget):
        reference=game.capture()
        batch=CandidateBatch([self.row()],adapter.context(),budget.observation_deadline,clock=game.clock)
        with adapter.execution_scope(budget):
            return execute_candidate(adapter,batch,batch.id,0,reference,self.rules,
                clock=game.clock,stage_budget=budget)

    def test_soft_cutoff_during_input_releases_then_observes_without_using_return_time(self):
        clock=Clock();game=TimedGame(clock);adapter=TimedAdapter(game)
        budget=ExecutionStageBudget(.8,3.,20.,clock)
        result=self.execute(game,adapter,budget)
        self.assertTrue(result['recovered']);self.assertTrue(result['pose_reliable'])
        self.assertEqual(adapter.reads,2)
        self.assertLess(clock(),budget.observation_deadline)
        self.assertTrue(all(at<budget.input_deadline for flags,at in game.sent if flags not in (4,16)))
        self.assertIn(4,[flags for flags,_ in game.sent])
        self.assertEqual(game.scopes,[]);self.assertIsNone(adapter._stage_budget)
        np.testing.assert_allclose(result['actual_pose'],game.pose[:2])

    def test_ocr_soft_timeout_preserves_known_pose_for_return_without_claiming_hex(self):
        clock=Clock();game=TimedGame(clock);game.point_seconds=.005
        adapter=TimedAdapter(game,soft_ocr_timeout=True)
        budget=ExecutionStageBudget(2.,3.,20.,clock)
        result=self.execute(game,adapter,budget)
        self.assertEqual(clock(),3.)
        self.assertEqual(adapter.reads,1)
        self.assertFalse(result['verified']);self.assertTrue(result['pose_reliable'])
        self.assertEqual(result['actual_colors'],[None]*3)
        np.testing.assert_allclose(result['actual_pose'],game.pose[:2])

    def test_slow_recovery_ocr_does_not_restart_reading_after_its_soft_deadline(self):
        clock=Clock();game=TimedGame(clock)
        adapter=TimedAdapter(game,soft_ocr_timeout=True)
        budget=ExecutionStageBudget(.8,3.,20.,clock)
        result=self.execute(game,adapter,budget)
        self.assertEqual(adapter.reads,1)
        self.assertEqual(clock(),3.)
        self.assertFalse(result['verified']);self.assertTrue(result['pose_reliable'])
        self.assertEqual(result['actual_colors'],[None]*3)
        np.testing.assert_allclose(result['actual_pose'],game.pose[:2])

    def test_live_choice_passes_short_trial_budget_without_shortening_hard_deadline(self):
        clock=Clock();game=TimedGame(clock);adapter=TimedAdapter(game)
        adapter.verified_frame=game.pose.copy()
        report=dict(adapter=adapter,selection_deadline=20.,pose_reference=game.pose.copy(),
                    actual_pose=game.pose[:2].tolist(),runtime={})
        owner=SimpleNamespace(event=lambda *a,**k:None)
        def timed_batch(rows,context,deadline):
            return CandidateBatch(rows,context,deadline,clock=clock)
        with patch('atlas_live_adapter.time.monotonic',clock), \
             patch('atlas_live_adapter.CandidateBatch',side_effect=timed_batch):
            result=choice_current(owner,report,self.row(),self.rules,selection_deadline=5.)
        self.assertTrue(result['recovered'])
        self.assertLess(clock(),5.)
        self.assertEqual(report['selection_deadline'],20.)
        self.assertEqual(game.until,20.)
        self.assertTrue(all(at<1.5 for flags,at in game.sent if flags not in (4,16)))
        self.assertIsNone(adapter._stage_budget)

    def test_live_ocr_deadline_is_converted_to_soft_stage_outcome(self):
        clock=Clock();game=TimedGame(clock)
        scene=SimpleNamespace(cards=[(0,0,5,5)]*3,markers=[(2,8)]*3)
        adapter=Adapter(game,scene,'ocr');image=np.zeros((10,10,3),np.uint8)
        budget=ExecutionStageBudget(1.,2.,20.,clock)
        with adapter.execution_scope(budget), \
             patch('atlas_runtime.read_codes',side_effect=TimeoutError('OCR observation deadline expired')) as read:
            with self.assertRaises(StageBudgetExceeded):adapter.read_codes(image)
            self.assertEqual(read.call_args.kwargs['deadline'],2.)
            self.assertIs(read.call_args.kwargs['clock'],clock)

    def test_late_registration_keeps_measurement_but_blocks_further_observation(self):
        clock=Clock();game=TimedGame(clock)
        adapter=Adapter(game,SimpleNamespace(),'motion')
        registration=dict(matrix=[[1,0,4],[0,1,0]])
        def delayed(*args):clock.advance(2.);return registration
        with adapter.execution_scope(ExecutionStageBudget(.5,1.,20.,clock)), \
             patch('atlas_runtime.motion',side_effect=delayed):
            self.assertIs(adapter.motion(np.eye(3),np.eye(3)),registration)
            self.assertTrue(adapter.last_motion_diagnostics['observation_deadline_reached'])
            with self.assertRaises(StageBudgetExceeded):adapter.capture()

    def test_unexpected_drag_retains_late_measured_pose_without_retry_or_ocr(self):
        clock=Clock();game=TimedGame(clock);game.point_seconds=.005
        send=game.send
        def reversed_response(flags,dx=0,dy=0):
            send(flags,-dx,-dy)
        game.send=reversed_response
        class MeasuredAdapter(TimedAdapter):
            motion=Adapter.motion
        adapter=MeasuredAdapter(game)
        budget=ExecutionStageBudget(2.,3.,20.,clock)
        registrations=[]
        def measured_registration(before,after,scene,diagnostics):
            registrations.append((before.copy(),after.copy()))
            clock.advance(.05 if len(registrations)==1 else 3.)
            diagnostics.update(passed=True)
            return dict(matrix=(after@np.linalg.inv(before))[:2].tolist(),angle=0.,scale=1.)
        with patch('atlas_runtime.motion',side_effect=measured_registration):
            result=self.execute(game,adapter,budget)
        self.assertGreater(clock(),budget.observation_deadline)
        self.assertLess(clock(),budget.hard_deadline)
        self.assertEqual(len(registrations),2)
        self.assertTrue(adapter.last_motion_diagnostics['observation_deadline_reached'])
        self.assertEqual(adapter.reads,0)
        self.assertTrue(result['recovered']);self.assertTrue(result['pose_reliable'])
        self.assertFalse(result['verified']);self.assertFalse(result['positioning_complete'])
        self.assertEqual(result['recovery_reason'],'Unexpected image displacement')
        self.assertEqual(result['actual_colors'],[None]*3)
        self.assertLess(game.pose[0,2],0.)
        np.testing.assert_allclose(result['actual_pose'],game.pose[:2])
        np.testing.assert_allclose(adapter.verified_frame,game.pose)
        self.assertTrue(all(at<budget.input_deadline for flags,at in game.sent if flags not in (4,16)))
        self.assertEqual(game.scopes,[])
        self.assertIn(4,[flags for flags,_ in game.sent])

    def test_production_final_input_scope_uses_soft_exception_and_always_releases(self):
        game=object.__new__(CaptureGame);game.check=lambda:None
        with patch('live_atlas_capture.time.monotonic',return_value=2.), \
             patch('live_atlas_capture.Game.send') as send:
            with game.input_scope(1.,lambda:None,expiry_factory=StageBudgetExceeded):
                with self.assertRaises(StageBudgetExceeded):game.send(1)
                game.send(4);game.send(16)
            self.assertEqual([call.args[0] for call in send.call_args_list],[4,16])
            self.assertEqual(game._input_scopes,[])

    def test_f9_during_input_never_runs_recovery(self):
        clock=Clock();game=TimedGame(clock);adapter=TimedAdapter(game)
        original=game.send
        def stop_after_move(flags,dx=0,dy=0):
            original(flags,dx,dy)
            if flags==1:game.stop=True
        game.send=stop_after_move
        with self.assertRaises(InterruptedError):
            self.execute(game,adapter,ExecutionStageBudget(5.,8.,20.,clock))
        self.assertEqual(adapter.reads,0)
        self.assertEqual(game.scopes,[])
        self.assertIn(4,[flags for flags,_ in game.sent])


if __name__=='__main__':unittest.main()
