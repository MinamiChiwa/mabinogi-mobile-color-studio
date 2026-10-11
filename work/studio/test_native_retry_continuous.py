"""Continuous retry zoom preserves per-notch input and final actual feedback."""
import copy
import json
import unittest
from unittest.mock import patch

from input_gestures import PointerGesture
from native_input_response import replay_native_route
from native_live.retry import retry_budget
import test_native_retry as retry_fixture
import test_native_protected_io as protected_fixture


class ContinuousRetryIO(retry_fixture.RetryIO):
    def perform_retry_reset(self, route, label, deadline):
        self.check(deadline)
        gesture=PointerGesture('wheel',tuple(map(tuple,route[0]['points'])),
            wheel_steps=sum(g['wheel_steps'] for g in route)).record()
        self.actions.append(gesture);self.t+=gesture['input_seconds']+.1
        if not self.stuck_wheel:
            self.pose=replay_native_route(self.pose,route,self.geometry,self.settings,
                wheel_delta_per_step=1.,sample_policy='all_recorded_points')['final_pose']
        return dict(completed=not self.unknown_input,released=True,gesture=gesture,
            actual_trace=[dict(actual_client=list(p)) for p in gesture['points']])


class ContinuousRetryControllerTests(unittest.TestCase):
    def run_retry(self,io,retry_at=34.):
        runner=retry_fixture.NativeRetryTests()
        requested,event,events=runner.once_ready(io,retry_at=retry_at)
        result=runner.run_loop(io,requested,event)
        return result,events

    def test_recorded_reset_is_one_input_with_only_final_actual_color_verification(self):
        for count in (2,3):
            with self.subTest(count=count):
                io=ContinuousRetryIO(count,scale=1.8610960245132446)
                result,events=self.run_retry(io)
                reset_steps=[s for s in result['steps'] if s['purpose']=='retry_reset']
                self.assertEqual([s['requested_gesture']['wheel_steps'] for s in reset_steps],[-131])
                self.assertEqual(result['retry_epochs'],1,result.get('error'))
                self.assertEqual(result['actual_input_attempts'],len(io.actions))
                self.assertEqual(result['effective_deadline'],90.)
                self.assertEqual(io.timer_grace_until,31.)
                self.assertEqual(reset_steps[0]['after']['pose']['scale'],.5)
                reset_labels=[o['label'] for o in result['observations'] if o['label'].startswith('retry_1_')]
                self.assertEqual(reset_labels,['retry_1_reference','retry_1_after'])
                self.assertEqual(result['best_actual_colors'],result['initial']['checkpoint']['client_hex'])
                self.assertEqual(result['actual_colors'],io.colors());self.assertTrue(result['best_current'])
                reset=result['steps'][0]
                self.assertEqual([g['wheel_steps'] for g in reset['requested_route']],[-32,-32,-32,-32,-3])
                self.assertTrue(reset['screenshot_verified'])
                self.assertEqual(reset['after']['pose'],reset['expected_pose'])

    def test_reset_endpoint_must_be_actual_minimum_before_search(self):
        io=ContinuousRetryIO();io.stuck_wheel=True
        result,events=self.run_retry(io)
        self.assertEqual(len(io.actions),1)
        self.assertEqual(result['stop_reason'],'retry_minimum_unconfirmed')
        self.assertEqual(result['retry_epochs'],0)
        self.assertFalse(any(e['event']=='native_retry_reset' and e.get('status')=='searching' for e in events))

    def test_unknown_continuous_input_cannot_start_search(self):
        io=ContinuousRetryIO();io.unknown_input=True
        result,events=self.run_retry(io)
        self.assertEqual(result['stop_reason'],'input_outcome_unknown')
        self.assertEqual(result['retry_epochs'],0)
        self.assertEqual(len(io.actions),1)

    def test_dropped_last_notch_is_corrected_from_actual_endpoint_without_global_search(self):
        io=ContinuousRetryIO();perform=io.perform_retry_reset;once=[False]
        def drop_last(route,label,deadline):
            if not once[0]:
                once[0]=True
                short=copy.deepcopy(route)
                last=short[-1]
                short[-1]=PointerGesture('wheel',tuple(map(tuple,last['points'])),wheel_steps=last['wheel_steps']+1).record()
                receipt=perform(route,label,deadline)
                io.pose=replay_native_route(dict(position=[0.,0.],scale=1.,rotation_degrees=0.),
                    short,io.geometry,io.settings,wheel_delta_per_step=1.,sample_policy='all_recorded_points')['final_pose']
                return receipt
            return perform(route,label,deadline)
        io.perform_retry_reset=drop_last
        result,events=self.run_retry(io)
        self.assertEqual(result['retry_epochs'],1,result.get('error'))
        reset_steps=[s for s in result['steps'] if s['purpose']=='retry_reset']
        self.assertEqual([s['requested_gesture']['wheel_steps'] for s in reset_steps],[-69,-1])
        self.assertEqual(reset_steps[-1]['after']['pose']['scale'],.5)
        self.assertEqual(result['retries'][0]['correction_passes'],1)

    def test_continuous_budget_pays_one_preparation_and_one_final_visual_read(self):
        route=[PointerGesture('wheel',((260,260),),wheel_steps=n).record() for n in (-32,-32,-32,-32,-3)]
        costs=dict(native=[1.312,1.375,1.281],closing_visual=[3.359,2.859,3.375],input=[.434,.419,.398])
        budget=retry_budget(route,costs,include_reference=True,continuous=True)
        self.assertAlmostEqual(budget['reset_input_seconds'],2.458)
        self.assertAlmostEqual(budget['required_seconds'],8.292)
        self.assertEqual(budget['reset_actions'],1)
        self.assertEqual(budget['required_actions'],2)
        empty=retry_budget([],costs,include_reference=False,continuous=True)
        self.assertEqual(empty['reset_allowance_seconds'],0.)
        self.assertEqual(empty['reset_actions'],0)


class ContinuousRetryInputTests(unittest.TestCase):
    def setUp(self):
        self.fixture=protected_fixture.NativeProtectedIOTests();self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.io=self.fixture.io;self.releases=[];self.io.game.send=self.releases.append
        self.route=[PointerGesture('wheel',((250,250),),wheel_steps=n).record() for n in (-32,-32,-5)]

    def reset(self,route=None,deadline=30.):
        method=getattr(self.io,'perform_retry_reset',None)
        self.assertTrue(callable(method),'Continuous retry input boundary is missing')
        return method(self.route if route is None else route,'retry_1_zoom',deadline)

    def test_continuous_receipt_and_per_notch_cadence_are_preserved(self):
        receipt=self.reset()
        self.assertTrue(receipt['completed']);self.assertTrue(receipt['released'])
        self.assertEqual(self.releases,[4,16])
        self.assertEqual(self.io.input_attempts,1)
        self.assertEqual(receipt['gesture']['wheel_steps'],-69)
        self.assertEqual(receipt['gesture']['timing']['point_interval'],.018)
        self.assertAlmostEqual(receipt['gesture']['input_seconds'],1.342)
        self.assertEqual(receipt['model_route'],self.route)
        saved=json.loads((self.io.folder/'retry_1_zoom.input.json').read_text())
        self.assertEqual(saved['model_route'],json.loads(json.dumps(self.route)))
        self.assertEqual(self.fixture.backend_reads,2)

    def test_invalid_retry_route_never_sends_input(self):
        cases=[[],self.route*22,
            [PointerGesture('wheel',((250,250),),wheel_steps=1).record()],
            [self.route[0],PointerGesture('wheel',((251,250),),wheel_steps=-1).record()],
            [PointerGesture('wheel',((200,200),),wheel_steps=-1).record()],
            [PointerGesture('wheel',((250,250),),wheel_steps=-33).record()],
            [self.fixture.record]]
        for route in cases:
            with self.subTest(route=route[:1]):
                with self.assertRaises(ValueError):self.reset(route)
                self.fixture.assert_no_inputs()

    def test_changed_binding_or_insufficient_time_sends_no_wheel(self):
        self.fixture.backend.observation['session_token']=['different']
        with self.assertRaises(ValueError):self.reset()
        self.fixture.assert_no_inputs()
        self.fixture.backend.observation=copy.deepcopy(self.io.last_observation)
        with self.assertRaises(TimeoutError):self.reset(deadline=11.)
        self.fixture.assert_no_inputs()

    def test_generic_input_still_rejects_more_than_32_wheel_steps(self):
        with self.assertRaises(ValueError):
            self.io.perform_candidate(PointerGesture('wheel',((250,250),),wheel_steps=-69).record(),'ordinary',30.)
        self.fixture.assert_no_inputs()

    def test_actual_windows_wheel_loop_checks_stop_focus_and_geometry_every_notch(self):
        from platform_win import Game
        for reason in ('F9','focus','geometry','deadline','send_failure'):
            with self.subTest(reason=reason):
                game=Game.__new__(Game);events=[];waits=[]
                game.geometry=lambda:(0,0,500,500);game.move_to=lambda p:None
                self.io.game=game;game.check=self.io._input_guard
                self.io.stop.clear();self.io.input_attempts=0;self.io.sent_any=False
                self.io.f9_pressed=lambda:reason=='F9' and len(events)>=7
                def focus_check():
                    if len(events)>=7 and reason in ('focus','geometry'):
                        raise RuntimeError('游戏失去焦点' if reason=='focus' else '窗口位置或尺寸已变化')
                self.io.original_game_check=focus_check
                def send(flags,**kw):
                    if flags==0x800:
                        if reason=='send_failure' and len(events)==7:raise RuntimeError('SendInput rejected')
                        events.append(kw['data'])
                    else:self.releases.append(flags)
                game.send=send
                def sleep(seconds):
                    waits.append(seconds)
                    self.fixture.clock.now+=seconds
                    if reason=='deadline' and len(events)>=7:self.fixture.clock.now=30.
                self.fixture.clock.now=10.
                with patch('platform_win.time.sleep',sleep):
                    with self.assertRaises((InterruptedError,TimeoutError,RuntimeError)):self.reset()
                self.assertEqual(events,[-120]*7)
                self.assertEqual(waits,[.018]*7)
                self.assertFalse(self.io._performing_input)
                saved=json.loads((self.io.folder/'retry_1_zoom.input.json').read_text())
                self.assertFalse(saved['completed']);self.assertTrue(saved['released'])
                self.assertEqual(self.releases[-2:],[4,16])

    def test_actual_windows_reset_has_no_group_pauses_or_repeated_cursor_moves(self):
        from platform_win import Game
        game=Game.__new__(Game);wheels=[];moves=[];waits=[]
        game.geometry=lambda:(-1280,100,500,500);game.move_to=moves.append
        self.io.game=game;game.check=self.io._input_guard
        def send(flags,**kw):
            if flags==0x800:wheels.append(kw['data'])
            else:self.releases.append(flags)
        game.send=send
        def sleep(seconds):
            waits.append(seconds);self.fixture.clock.now+=seconds
        with patch('platform_win.time.sleep',sleep):receipt=self.reset()
        self.assertTrue(receipt['completed'])
        self.assertEqual(wheels,[-120]*69)
        self.assertEqual(moves,[(250,250)])
        self.assertEqual(waits,[.018]*69+[.1])


if __name__=='__main__':unittest.main()
