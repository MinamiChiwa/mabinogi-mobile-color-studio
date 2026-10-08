import tempfile
import unittest
import threading
import json
import time
import numpy as np
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch,MagicMock
from PIL import Image
from atlas_live_adapter import (acquire_current,_execute_recorded,observe_current,
                                 callbacks,_candidate_is_no_worse,
                                 _automatic_route_allowed)
from atlas_pose import homogeneous
from platform_win import Interrupted
from atlas_service import AtlasService


class LiveAdapterTests(unittest.TestCase):
    def test_automatic_route_gate_allows_translation_without_profile(self):
        row=dict(execution_budget={'actions':{'drag':2}},
                 route_stability={'passed':True,'samples_complete':True,
                                  'response_profile_verified':False},
                 planned_route={'game_response_verified':False})
        self.assertTrue(_automatic_route_allowed(row))

    def test_automatic_route_gate_rejects_unverified_rotation_and_wheel(self):
        for action in ('rotate','wheel'):
            row=dict(execution_budget={'actions':{action:1}},
                     route_stability={'passed':True,'landing_safe':True,
                                      'response_profile_verified':False},
                     planned_route={'game_response_verified':False})
            self.assertFalse(_automatic_route_allowed(row))

    def test_automatic_route_gate_requires_both_certificates_for_transforms(self):
        row=dict(execution_budget={'actions':{'rotate':1}},
                 route_stability={'passed':True,'landing_safe':True,
                                  'response_profile_verified':True},
                 planned_route={'game_response_verified':False})
        self.assertFalse(_automatic_route_allowed(row))
        row['planned_route']['game_response_verified']=True
        self.assertTrue(_automatic_route_allowed(row))

    def test_replan_candidate_quality_is_monotonic_within_tier(self):
        # A measured-pose fallback may differ by a small resampling amount,
        # but must not silently replace a good route with a materially worse
        # compromise (the regression seen after repeated actions).
        current=dict(accepted=False,maximum=12.,average=8.)
        self.assertTrue(_candidate_is_no_worse(dict(accepted=False,maximum=12.9,average=9.), current))
        self.assertFalse(_candidate_is_no_worse(dict(accepted=False,maximum=14.,average=9.), current))

    def test_replan_preserves_acceptance_tier(self):
        accepted=dict(accepted=True,maximum=4.,average=2.)
        # A lower predicted error cannot compensate for losing the accepted
        # tier; execution must retain the already publishable route.
        self.assertFalse(_candidate_is_no_worse(dict(accepted=False,maximum=0.,average=0.), accepted))
        self.assertTrue(_candidate_is_no_worse(dict(accepted=True,maximum=4.5,average=3.), accepted))
    def current_fixture(self,now=100.):
        scene=SimpleNamespace(board=(20,25,80,85),markers=[(30,60),(50,60),(70,60)],
                              cards=[(10,10,10,10),(30,10,10,10),(50,10,10,10)])
        image=np.zeros((100,100,3),np.uint8)
        game=SimpleNamespace(until=now+20.,check=MagicMock(),capture=MagicMock(return_value=image),
                             pause=MagicMock(),perform_gesture=MagicMock(),move_to=MagicMock(),
                             wheel=MagicMock(),drag=MagicMock(),rotate=MagicMock(),click=MagicMock())
        artifact=dict(game=game,scene=scene,deadline=now+10.,game_deadline=now+20.)
        owner=SimpleNamespace(event=lambda *a,**k:None)
        rules=[dict(enabled=True,exact=False,colors=['#112233'],tolerance=8)]*3
        return owner,artifact,rules,game

    def test_live_callbacks_wire_read_only_current_observation(self):
        self.assertIs(callbacks('capture').observe_current,observe_current)
        owner,artifact,rules,game=self.current_fixture()
        with patch('atlas_live_adapter.time.monotonic',return_value=100.), \
             patch('atlas_runtime.read_codes',return_value=['#112233']*3) as reader, \
             patch('atlas_live_adapter.bind_candidate') as binder:
            result=observe_current(owner,artifact,rules,reason='atlas_quality_failed',selection_deadline=106.)
        self.assertTrue(result['verified']);self.assertTrue(result['observed_accepted'])
        self.assertFalse(result['accepted']);self.assertIsNone(result['candidate_id'])
        self.assertIsNone(result['actual_pose']);self.assertFalse(result['best_result_current'])
        self.assertEqual(result['actual_colors'],['#112233']*3)
        self.assertEqual(result['predicted_colors'],[None]*3)
        self.assertEqual(game.capture.call_count,2)
        self.assertEqual(result['observed_frames'],2)
        # Identical full cards may reuse the validated OCR, but two independent
        # screen captures remain mandatory and bounded by the same deadline.
        self.assertEqual(reader.call_count,1)
        self.assertAlmostEqual(reader.call_args.kwargs['deadline'],103.5)
        binder.assert_not_called()
        for method in (game.perform_gesture,game.move_to,game.wheel,game.drag,game.rotate,game.click):
            method.assert_not_called()

    def test_live_service_quality_failure_ends_on_current_hex_without_atlas_route(self):
        owner,artifact,rules,game=self.current_fixture();events=[]
        owner.event=lambda kind,**data:events.append((kind,data))
        live=callbacks('capture')
        with patch('atlas_live_adapter.time.monotonic',return_value=100.), \
             patch('atlas_live_adapter.acquire_current',return_value=artifact), \
             patch('atlas_live_adapter.build_current',return_value=dict(quality_gate={'passed':False})), \
             patch('atlas_runtime.read_codes',return_value=['#112233']*3):
            # Factory captures build_current by value; replace its build seam
            # only, while keeping the real observer wiring unchanged.
            live.build=lambda *a,**k:dict(quality_gate={'passed':False})
            result=AtlasService(live).run(owner,rules,selection_deadline=108.)
        self.assertEqual(events[-1][0],'atlas_recovery')
        self.assertTrue(result['verified']);self.assertTrue(result['observed_accepted'])
        self.assertFalse(result['accepted']);self.assertFalse(result['positioning_complete'])
        self.assertIsNone(result['actual_pose']);self.assertIsNone(result['candidate_id'])
        self.assertEqual(result['actual_colors'],['#112233']*3)
        game.perform_gesture.assert_not_called();game.move_to.assert_not_called()

    def test_current_observation_respects_earliest_game_deadline(self):
        owner,artifact,rules,game=self.current_fixture()
        game.until=102.;artifact['deadline']=101.5
        with patch('atlas_live_adapter.time.monotonic',return_value=100.), \
             patch('atlas_runtime.read_codes',return_value=['#112233']*3) as reader:
            result=observe_current(owner,artifact,rules,selection_deadline=101.)
        self.assertTrue(result['verified'])
        self.assertAlmostEqual(reader.call_args.kwargs['deadline'],100.75)
        self.assertEqual(game.until,102.)

    def test_current_observation_checks_safety_before_capturing(self):
        owner,artifact,rules,game=self.current_fixture()
        game.check.side_effect=Interrupted('focus changed')
        with patch('atlas_runtime.read_codes') as reader:
            with self.assertRaises(Interrupted):observe_current(owner,artifact,rules)
        game.capture.assert_not_called();reader.assert_not_called()
        owner,artifact,rules,game=self.current_fixture()
        with patch('atlas_live_adapter.time.monotonic',return_value=artifact['deadline']), \
             patch('atlas_runtime.read_codes') as reader:
            with self.assertRaises(Interrupted):observe_current(owner,artifact,rules)
        game.capture.assert_not_called();reader.assert_not_called()

    def test_current_observation_returns_unknown_after_ordinary_ocr_failure(self):
        owner,artifact,rules,game=self.current_fixture()
        with patch('atlas_live_adapter.time.monotonic',return_value=100.), \
             patch('atlas_runtime.read_codes',side_effect=RuntimeError('OCR unavailable')) as reader:
            result=observe_current(owner,artifact,rules)
        self.assertFalse(result['verified']);self.assertEqual(result['actual_colors'],[None]*3)
        self.assertEqual(reader.call_count,1);self.assertEqual(game.capture.call_count,1)
        self.assertIn('OCR unavailable',result['observation_error'])

    def test_current_observation_ocr_fault_cannot_hide_new_safety_interrupt(self):
        owner,artifact,rules,game=self.current_fixture()
        stopped=[False]
        def check():
            if stopped[0]:raise Interrupted('F9 after OCR failure')
        def read(*a,**k):
            stopped[0]=True
            raise RuntimeError('OCR unavailable')
        game.check.side_effect=check
        with patch('atlas_live_adapter.time.monotonic',return_value=100.), \
             patch('atlas_runtime.read_codes',side_effect=read) as reader:
            with self.assertRaisesRegex(Interrupted,'F9 after OCR failure'):
                observe_current(owner,artifact,rules)
        self.assertEqual(game.capture.call_count,1);self.assertEqual(reader.call_count,1)
        game.perform_gesture.assert_not_called()

    def test_current_observation_stops_when_later_safety_check_changes(self):
        owner,artifact,rules,game=self.current_fixture();checks=[0]
        def check():
            checks[0]+=1
            if checks[0]>=4:raise Interrupted('F9')
        game.check.side_effect=check
        with patch('atlas_live_adapter.time.monotonic',return_value=100.), \
             patch('atlas_runtime.read_codes',return_value=['#112233']*3) as reader:
            with self.assertRaises(Interrupted):observe_current(owner,artifact,rules)
        self.assertEqual(game.capture.call_count,1);self.assertEqual(reader.call_count,1)

    def test_current_observation_soft_ocr_budget_cannot_consume_whole_game_countdown(self):
        owner,artifact,rules,game=self.current_fixture();now=[100.]
        def read(*a,**kw):
            self.assertEqual(kw['deadline'],103.5)
            now[0]=103.6
            return ['#112233']*3
        with patch('atlas_live_adapter.time.monotonic',side_effect=lambda:now[0]), \
             patch('atlas_runtime.read_codes',side_effect=read) as reader:
            result=observe_current(owner,artifact,rules)
        self.assertFalse(result['verified']);self.assertEqual(result['actual_colors'],[None]*3)
        self.assertEqual(game.capture.call_count,1);self.assertEqual(reader.call_count,1)

    def test_current_observation_does_not_start_with_insufficient_time_or_missing_artifact(self):
        owner,artifact,rules,game=self.current_fixture()
        with patch('atlas_live_adapter.time.monotonic',return_value=100.), \
             patch('atlas_runtime.read_codes') as reader:
            result=observe_current(owner,artifact,rules,selection_deadline=100.1)
            self.assertIsNone(observe_current(owner,{},rules))
        self.assertFalse(result['verified']);self.assertEqual(result['observed_frames'],0)
        game.capture.assert_not_called();reader.assert_not_called()

    def test_return_guard_receives_global_current_and_projected_poses(self):
        adapter=SimpleNamespace(check=lambda:None)
        # Use a non-identity scale/translation reference to catch a missing
        # conversion or reversed multiplication at the production wrapper.
        reference_pose=homogeneous([[1.2,0.,31.],[0.,1.2,-14.]])
        actual=homogeneous([[1.,0.,-8.],[0.,1.,11.]])
        projected=homogeneous([[0.,-1.,50.],[1.,0.,-20.]])@actual
        received=[]
        def guard(current,upcoming,projected_pose=None):
            received.append((current.copy(),upcoming,
                None if projected_pose is None else projected_pose.copy()))
            return dict(allowed=True)
        def execute(*args,**kwargs):
            self.assertTrue(adapter.return_guard(actual,2.5,projected_pose=projected)['allowed'])
            self.assertTrue(adapter.return_guard(actual,1.75,projected_pose=None)['allowed'])
            return dict(verified=True)
        owner=SimpleNamespace(event=lambda *a,**k:None)
        report=dict(adapter=adapter,actual_pose=reference_pose[:2].tolist())
        batch=SimpleNamespace(id='batch',deadline=time.monotonic()+60)
        with patch('atlas_live_adapter.execute_candidate',side_effect=execute):
            _execute_recorded(owner,report,{'id':1},[],batch,None,return_guard=guard)
        np.testing.assert_allclose(received[0][0],actual@reference_pose)
        np.testing.assert_allclose(received[0][2],projected@reference_pose)
        self.assertEqual(received[0][1],2.5)
        self.assertIsNone(received[1][2])

    def test_execution_without_guard_clears_the_previous_callback(self):
        adapter=SimpleNamespace(check=lambda:None,return_guard=lambda *a,**k:None)
        owner=SimpleNamespace(event=lambda *a,**k:None)
        report=dict(adapter=adapter)
        batch=SimpleNamespace(id='batch',deadline=time.monotonic()+60)
        with patch('atlas_live_adapter.execute_candidate',return_value=dict(verified=True)):
            _execute_recorded(owner,report,{'id':1},[],batch,None)
        self.assertIsNone(adapter.return_guard)

    def test_failure_saves_both_existing_motion_frames_and_diagnostics(self):
        with tempfile.TemporaryDirectory() as folder:
            adapter=SimpleNamespace(last_motion_before=None,last_motion_after=None,
                                    last_motion_diagnostics=None,check=lambda:None)
            before=np.full((12,12,3),20,np.uint8);after=before+10
            diagnostics={'passed':False,'reason':'insufficient_inliers'}
            def fail(*args,**kwargs):
                adapter.last_motion_before=before;adapter.last_motion_after=after
                adapter.last_motion_diagnostics=diagnostics;adapter.last_frame=after
                kwargs['emit']('atlas_command',{'step':1,'action':'drag','command':[-49,80]})
                raise RuntimeError('配准失败')
            report=dict(adapter=adapter,capture_folder=Path(folder))
            owner=SimpleNamespace(event=lambda *a,**k:None)
            with patch('atlas_live_adapter.execute_candidate',side_effect=fail):
                with self.assertRaises(RuntimeError):
                    _execute_recorded(owner,report,{'id':1},[],SimpleNamespace(id='batch',deadline=time.monotonic()+60),before)
            self.assertTrue(report['diagnostic_write'].wait(5))
            data=json.loads((Path(folder)/'execution/attempt-01.json').read_text(encoding='utf-8'))
            self.assertEqual(data['last_registration'],diagnostics)
            self.assertEqual(data['events'][0]['command'],[-49,80])
            for label,expected in (('before',before),('after',after)):
                saved=Image.open(Path(folder)/'execution'/data['motion_frames'][label])
                np.testing.assert_array_equal(np.array(saved),expected)
            # A later F9 before capture must not attribute the previous pair
            # to a new attempt, and saving never requests another screenshot.
            with patch('atlas_live_adapter.execute_candidate',side_effect=InterruptedError('F9')):
                with self.assertRaises(InterruptedError):
                    _execute_recorded(owner,report,{'id':1},[],SimpleNamespace(id='batch',deadline=time.monotonic()+60),before)
            self.assertTrue(report['diagnostic_write'].wait(5))
            second=json.loads((Path(folder)/'execution/attempt-02.json').read_text(encoding='utf-8'))
            self.assertIsNone(second['last_registration']);self.assertEqual(second['motion_frames'],{})

    def test_failed_execution_saves_last_frame_without_recapturing(self):
        with tempfile.TemporaryDirectory() as folder:
            adapter=SimpleNamespace(last_frame=np.zeros((12,12,3),np.uint8),check=lambda:None)
            report=dict(adapter=adapter,capture_folder=Path(folder))
            owner=SimpleNamespace(event=lambda *a,**k:None)
            with patch('atlas_live_adapter.execute_candidate',side_effect=InterruptedError('F9')):
                with self.assertRaises(InterruptedError):
                    _execute_recorded(owner,report,{'id':1},[],SimpleNamespace(id='batch',deadline=time.monotonic()+60),None)
            self.assertTrue(report['diagnostic_write'].wait(5))
            data=json.loads((Path(folder)/'execution/attempt-01.json').read_text())
            self.assertEqual(data['error'],'F9');self.assertIsNone(data['result'])
            self.assertTrue((Path(folder)/'execution/attempt-01.png').is_file())

    def test_acquire_waits_for_manual_entry(self):
        with tempfile.TemporaryDirectory() as folder:
            target=object()
            owner=SimpleNamespace(stop=threading.Event())
            with patch('atlas_live_adapter.acquire') as acquire:
                acquire.return_value={'folder':folder}
                result=acquire_current(owner,[],folder,
                                       strategy='grid',entry_size=(1280,960),target=target,activate=True)
                self.assertEqual(result['folder'],folder)
                self.assertEqual(acquire.call_args.args,(Path(folder),None))
                self.assertEqual(acquire.call_args.kwargs['strategy'],'grid')
                self.assertEqual(acquire.call_args.kwargs['row_stagger'],.05)
                self.assertIs(acquire.call_args.kwargs['target'],target)
                self.assertTrue(acquire.call_args.kwargs['activate'])
                self.assertEqual(acquire.call_args.kwargs['entry_size'],(1280,960))
                self.assertIs(acquire.call_args.kwargs['stop'],owner.stop)


if __name__=='__main__':unittest.main()
