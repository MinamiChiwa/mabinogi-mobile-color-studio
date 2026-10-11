"""Recorded session bindings stop input and retain separate screenshot history."""
import copy
import importlib
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from native_live.project_probe_io import ProjectProbeIO
from native_live.controller import run_goal_loop
from native_input_response import InputSettings
from test_support import read_local_fixture_text,load_local_palette_session


EVIDENCE=Path(__file__).resolve().parents[2]/'outputs/native-integration/verification/data3-audit-2026-10-11/input/sessions'


def recorded_session():
    folder=EVIDENCE/'20261011-140931-2f78e9ef'
    baseline=json.loads(read_local_fixture_text(folder/'native-baseline.json',encoding='utf-8'))
    result=json.loads(read_local_fixture_text(folder/'native-result.json',encoding='utf-8'))
    return folder,baseline,result


class ReadOnlyGame:
    def check(self):pass


class RecordedBackend:
    def __init__(self,baseline):
        self.observation=copy.deepcopy(baseline['baseline'])
        self.state=copy.deepcopy(self.observation)
        self.probe_error=None
        self.probe_calls=0
    def process_identity(self):return self.observation['process_identity']
    def probe(self,address,deadline,check):
        check();self.probe_calls+=1
        if self.probe_error:raise self.probe_error
        return copy.deepcopy(self.state)


class SessionStatusIOTests(unittest.TestCase):
    def setUp(self):
        _,self.baseline,_=recorded_session()
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.now=self.baseline['session_deadline_monotonic']-50.
        self.addCleanup(patch.stopall)
        patch('native_live.project_probe_io.time.monotonic',lambda:self.now).start()
        self.backend=RecordedBackend(self.baseline)
        self.io=ProjectProbeIO(self.backend,self.baseline,self.folder.name,game=ReadOnlyGame(),f9_pressed=lambda:False)
    def status_types(self):return importlib.import_module('native_live.session_status')
    def test_inactive_record_is_a_normal_palette_stop_with_saved_observation(self):
        self.backend.state=dict(active=False,session_token=None,pose=None,
            active_diagnostic=dict(instance_status='typed_inactive',capture_eligible=False))
        self.io.session_status_label='after_color'
        with self.assertRaises(ValueError) as raised:self.io.check(self.baseline['session_deadline_monotonic'])
        self.assertEqual(type(raised.exception).__name__,'PaletteEnded')
        diagnostic=json.loads((self.io.folder/'after_color.session-status.json').read_text())
        self.assertEqual(diagnostic['stop_reason'],'palette_ended')
        self.assertEqual(diagnostic['classification'],'normal_stop')
        self.assertIsNone(diagnostic['observed']['session_token'])
        self.assertEqual(diagnostic['active_diagnostic']['instance_status'],'typed_inactive')
        self.assertNotIn('expired',diagnostic)
        self.assertFalse(self.io.sent_any)
    def test_rebound_token_reports_the_changed_palette_pixel_field(self):
        self.backend.state['session_token'][5][1][1]='0'*64
        with self.assertRaises(ValueError) as raised:self.io.check(self.baseline['session_deadline_monotonic'])
        self.assertEqual(type(raised.exception).__name__,'SessionBindingChanged')
        diagnostic=self.io.last_session_diagnostic
        self.assertEqual(diagnostic['changed_fields'],['palette_pixels[1]'])
        self.assertEqual(diagnostic['expected']['session_token'],self.baseline['baseline']['session_token'])
        self.assertEqual(diagnostic['session_identity'],self.baseline['baseline']['process_identity'])
        self.assertFalse(self.io.sent_any)
    def test_process_replacement_is_a_binding_change_before_palette_probe(self):
        self.backend.observation['process_identity'][0]+=1
        with self.assertRaises(ValueError) as raised:self.io.check(self.baseline['session_deadline_monotonic'])
        self.assertEqual(type(raised.exception).__name__,'SessionBindingChanged')
        self.assertEqual(self.io.last_session_diagnostic['changed_fields'],['process_identity'])
        self.assertEqual(self.backend.probe_calls,0)
    def test_diagnostic_disk_failure_does_not_replace_palette_stop(self):
        self.backend.state=dict(active=False,session_token=None,pose=None)
        with patch.object(Path,'write_text',side_effect=OSError('read-only diagnostics')):
            with self.assertRaises(ValueError) as raised:self.io.check(self.baseline['session_deadline_monotonic'])
        self.assertEqual(type(raised.exception).__name__,'PaletteEnded')
        self.assertIn('read-only diagnostics',self.io.last_session_diagnostic['diagnostic_write_error'])
    def test_f9_is_checked_before_an_inactive_palette_is_classified(self):
        self.backend.state=dict(active=False,session_token=None,pose=None)
        self.io.f9_pressed=lambda:True
        with self.assertRaises(InterruptedError):self.io.check(self.baseline['session_deadline_monotonic'])
        self.assertEqual(self.backend.probe_calls,0)
        self.assertIsNone(getattr(self.io,'last_session_diagnostic',None))
    def test_repeated_torn_probe_has_a_retryable_observation_diagnostic(self):
        self.backend.probe_error=ValueError('Palette changed during probe')
        with patch('native_live.project_probe_io.time.sleep',lambda seconds:None):
            with self.assertRaises(ValueError) as raised:self.io.check(self.baseline['session_deadline_monotonic'])
        self.assertEqual(type(raised.exception).__name__,'SessionProbeUnstable')
        self.assertEqual(self.backend.probe_calls,3)
        self.assertEqual(self.io.last_session_diagnostic['classification'],'retryable_observation')
        self.assertIsNone(self.io.last_session_diagnostic['observed']['active'])
    def test_unknown_activity_is_not_reported_as_a_normal_palette_close(self):
        self.backend.state=dict(active=None,session_token=None,pose=None)
        with self.assertRaises(ValueError) as raised:self.io.check(self.baseline['session_deadline_monotonic'])
        self.assertEqual(type(raised.exception).__name__,'SessionProbeUnstable')
        self.assertEqual(self.io.last_session_diagnostic['classification'],'retryable_observation')
    def test_process_replaced_during_torn_probe_is_not_reported_as_unstable_read(self):
        original=self.backend.probe
        def probe(*args):
            self.backend.observation['process_identity'][0]+=1
            self.backend.probe_error=ValueError('Palette changed during probe')
            return original(*args)
        self.backend.probe=probe
        with self.assertRaises(ValueError) as raised:self.io.check(self.baseline['session_deadline_monotonic'])
        self.assertEqual(type(raised.exception).__name__,'SessionBindingChanged')
        self.assertEqual(self.io.last_session_diagnostic['changed_fields'],['process_identity'])
        self.assertEqual(self.backend.probe_calls,1)
    def test_checkpoint_color_export_token_change_stops_without_retrying_old_binding(self):
        from native_live.dye_action_checkpoint import record_action_checkpoint
        calls=[]
        self.backend.observe_motion=lambda *args,**kw:copy.deepcopy(self.baseline['baseline'])
        def capture(*args,**kw):
            calls.append(True);result=copy.deepcopy(self.baseline['capture'])
            result['session_token'][1]+=1
            return result
        self.backend.capture_validation_bundle=capture
        def pause(seconds):self.now+=seconds
        record=record_action_checkpoint(self.backend,self.baseline,'after_color',clock=lambda:self.now,
            pause=pause,timeout_seconds=1.,dwell_seconds=.1,poll_seconds=.1)
        self.assertEqual(record['stop_reason'],'binding_changed')
        self.assertEqual(record['failed_observation']['session_token'][1],1722990681601)
        self.assertEqual(len(calls),1)
    def test_f9_mid_checkpoint_propagates_once_without_retrying_observation(self):
        from native_live.dye_action_checkpoint import record_action_checkpoint
        cancellations=[];calls=[]
        stopped=InterruptedError('F9/stop requested')
        def check():
            calls.append(True)
            if len(calls)>1:
                cancellations.append(True);raise stopped
        def pause(seconds):self.now+=seconds
        with self.assertRaises(InterruptedError) as raised:
            record_action_checkpoint(self.backend,self.baseline,'after_color',clock=lambda:self.now,
                pause=pause,timeout_seconds=1.,dwell_seconds=.1,poll_seconds=.1,check=check)
        self.assertIs(raised.exception,stopped)
        self.assertEqual(len(cancellations),1)
        self.assertEqual(self.backend.probe_calls,0)
    def test_inactive_checkpoint_with_readonly_artifacts_keeps_the_palette_stop(self):
        inactive=dict(active=False,session_token=None,process_identity=self.backend.process_identity())
        record=dict(checkpoint_valid=False,stop_reason='palette_ended',failed_observation=inactive)
        with patch('native_live.project_probe_io.record_action_checkpoint',return_value=record):
            with patch.object(Path,'write_text',side_effect=OSError('read-only diagnostics')):
                with self.assertRaises(ValueError) as raised:self.io.checkpoint('after_color',self.baseline['session_deadline_monotonic'])
        self.assertEqual(type(raised.exception).__name__,'PaletteEnded')
        self.assertEqual(self.io.last_session_diagnostic['stage'],'checkpoint')


class RecordedGoalIO:
    def __init__(self):
        folder,self.reference,result=recorded_session()
        capture=folder/'native-captures'/Path(self.reference['capture']['capture_folder']).name
        self.session=load_local_palette_session(capture)
        self.settings=InputSettings(**self.reference['baseline']['motion']['settings'])
        self.current=copy.deepcopy(result['initial'])
        self.now=self.current['frames'][0]['captured_monotonic']-.05
        self.end=self.now+90.
        self.failure=None;self.reads=0;self.released=0;self.actions=[]
    def clock(self):return self.now
    def check(self,deadline):
        if self.failure:raise self.failure
        if self.now>=deadline:raise TimeoutError('recorded session deadline')
    planning_check=check
    def input_backend(self,deadline):
        self.check(deadline)
        return dict(process_identity=self.reference['baseline']['process_identity'],backend_object='archived',
            backend_type='MM.Client.Framework.InputSystem.InputManager',input_assistant='0x0',
            legacy_mouse_getter_rva='0x185310',viewport_origin=[0,0],viewport_scale=[1.,1.])
    def checkpoint(self,label,deadline):
        self.check(deadline);return dict(copy.deepcopy(self.current['checkpoint']),label=label)
    def frames(self,label,deadline):
        self.check(deadline);self.reads+=1
        frames=copy.deepcopy(self.current['frames'])
        self.now=frames[-1]['captured_monotonic']+.01
        return frames
    def pause(self,seconds):self.now+=seconds
    def perform_candidate(self,*args):raise AssertionError('Recorded read-only stop must not send input')
    def release(self):self.released+=1


class SessionStatusGoalTests(unittest.TestCase):
    def test_verified_shortening_prevents_timer_jitter_from_reextending_io_cap(self):
        from test_native_retry import RetryIO
        from test_native_deadline_controller import evidence_frames,metadata
        from native_live.session_deadline import verified_timer_extension
        io=RetryIO(count=2);io.t=149.
        binding=json.loads(io.binding)
        baseline=dict(stop_reason='passive_baseline_collected',instance_address=123,
            session_deadline_monotonic=180.,session_first_seen_monotonic=100.,timer_grace_until=130.,
            session_origin_observed_monotonic=100.,baseline_collected_monotonic=149.,
            session_first_seen_source='active_validation_observation',process_identity=binding[1],
            session_origin_evidence=dict(selected_address='0x7b',process_identity=binding[1]),
            baseline=dict(active=True,session_token=binding[0],process_identity=binding[1]),
            capture=dict(session_binding_verified=True,session_token=binding[0],process_identity=binding[1]))
        extension=metadata(io,initial=180.,maximum=200.);approved=[];calls=[0];current_id=[None]
        original_checkpoint=io.checkpoint
        def frames(label,deadline):
            calls[0]+=1;cp=original_checkpoint(label,deadline)
            if calls[0]<=3:
                first,second,seconds=((150.,154.,(50,46)),(160.,164.,(37,33)),(166.,170.,(32,28)))[calls[0]-1]
                io.t=second;return evidence_frames(cp,first,second,seconds)
            io.t+=.7;return evidence_frames(cp,io.t-.6,io.t,(None,None))
        def set_verified(end,evidence):
            expected=verified_timer_extension(evidence['checkpoint'],evidence['frames'],
                initial_engineering_deadline=180.,current_deadline=getattr(io,'accepted_session_deadline',180.),
                extension=extension,timer_grace_until=130.,now=io.t)
            if expected is None or expected['deadline']!=end:raise ValueError('Unapproved timer extension')
            approved.append(end);io.accepted_session_deadline=end
        def event(row):
            if row['event']=='native_candidate_ready':current_id[0]=row['current_candidate_id']
        def choose(batch_id,deadline):
            if calls[0]<3:return current_id[0]
            io.t=176.;return None
        def planner(*args,**kw):
            return dict(candidate=None,compromise_candidate=None,effective_deadline=kw['engineering_deadline'],
                result_classification='not_found_in_budget',candidate_pool=[])
        io.frames=frames;io.set_verified_session_deadline=set_verified
        result=run_goal_loop(io,io.session,io.settings,io.rules,engineering_deadline=180.,
            clock=io.clock,pause=io.pause,candidate_choice=choose,event=event,planner=planner,
            timer_grace_baseline=baseline,timer_deadline_extension=extension)
        self.assertEqual(approved,[190.]);self.assertEqual(result['effective_deadline'],187.)
        self.assertNotEqual(result['stop_reason'],'observation_failed',result.get('error'))
        self.assertTrue(result['accepted']);self.assertEqual(io.actions,[])
    def timer_baseline(self,io):
        # Reuse the exact archived capture and binding. These added timestamps
        # exercise a delayed controller invocation, not a claim of game age.
        baseline=copy.deepcopy(io.reference)
        seen=baseline['baseline']['read_finished_monotonic']
        baseline.update(session_first_seen_monotonic=seen,timer_grace_until=seen+30.,
            session_origin_observed_monotonic=seen,baseline_collected_monotonic=seen,
            session_first_seen_source='active_validation_observation',session_origin_evidence=dict(
                selected_address=hex(baseline['instance_address']),process_identity=baseline['process_identity']))
        return baseline
    def delayed_recorded_io(self):
        io=RecordedGoalIO()
        for frame in io.current['frames']:frame['captured_monotonic']+=30.
        io.now=io.current['frames'][0]['captured_monotonic']-.05
        io.end=io.reference['session_deadline_monotonic']
        return io
    def test_invalid_io_reference_cannot_borrow_timer_metadata_or_raise_attribute_error(self):
        for invalid in (None,[]):
            with self.subTest(reference=invalid):
                io=RecordedGoalIO();baseline=self.timer_baseline(io);io.reference=invalid
                rules=[dict(enabled=True,exact=True,colors=['#000000'],tolerance=0.) for _ in range(3)]
                with self.assertRaises(ValueError):
                    run_goal_loop(io,io.session,io.settings,rules,engineering_deadline=io.end,
                        clock=io.clock,pause=io.pause,timer_grace_baseline=baseline)
    def test_missing_legacy_io_reference_can_use_the_checked_baseline_binding(self):
        io=RecordedGoalIO();baseline=self.timer_baseline(io)
        backend=io.input_backend(io.end)
        del io.reference
        io.input_backend=lambda deadline:copy.deepcopy(backend)
        rules=[dict(enabled=True,exact=True,colors=[color],tolerance=0.) for color in io.current['checkpoint']['client_hex']]
        result=run_goal_loop(io,io.session,io.settings,rules,engineering_deadline=io.end,
            clock=io.clock,pause=io.pause,timer_grace_baseline=baseline)
        self.assertTrue(result['accepted'],result.get('error'))
        self.assertEqual(io.timer_grace_until,81122.312)
    def test_expired_timer_grace_does_not_expire_initial_visual_readiness(self):
        from native_live.dye_visual_readiness import VisualNotReady
        io=self.delayed_recorded_io();baseline=self.timer_baseline(io);original=io.frames
        def frames(label,deadline):
            if not io.reads:
                io.reads+=1;raise VisualNotReady('recorded overlay not yet ready')
            return original(label,deadline)
        io.frames=frames
        rules=[dict(enabled=True,exact=True,colors=[color],tolerance=0.) for color in io.current['checkpoint']['client_hex']]
        result=run_goal_loop(io,io.session,io.settings,rules,engineering_deadline=io.end,
            clock=io.clock,pause=io.pause,timer_grace_baseline=baseline)
        self.assertTrue(result['accepted'],result.get('error'));self.assertEqual(result['initial_visual_retries'],1)
        self.assertEqual(io.timer_grace_until,81122.312)
        self.assertEqual(result['observations'][0]['frames'][0]['timer_policy'],'unknown_advisory')
    def test_same_second_timer_pair_cannot_shorten_a_production_bound_session(self):
        io=self.delayed_recorded_io();baseline=self.timer_baseline(io)
        for frame in io.current['frames']:frame.update(remaining_seconds=17,timer_confidence='two_pass_agree')
        rules=[dict(enabled=True,exact=True,colors=[color],tolerance=0.) for color in io.current['checkpoint']['client_hex']]
        result=run_goal_loop(io,io.session,io.settings,rules,engineering_deadline=io.end,
            clock=io.clock,pause=io.pause,timer_grace_baseline=baseline)
        self.assertEqual(result['effective_deadline'],81160.125)
        self.assertTrue(result['accepted']);self.assertNotIn('deadline_shortenings',result)
    def test_verified_decreasing_pair_shortens_the_production_bound_session(self):
        io=self.delayed_recorded_io();baseline=self.timer_baseline(io)
        for frame,seconds in zip(io.current['frames'],(25,24)):
            frame.update(remaining_seconds=seconds,timer_confidence='two_pass_agree')
        rules=[dict(enabled=True,exact=True,colors=[color],tolerance=0.) for color in io.current['checkpoint']['client_hex']]
        result=run_goal_loop(io,io.session,io.settings,rules,engineering_deadline=io.end,
            clock=io.clock,pause=io.pause,timer_grace_baseline=baseline)
        self.assertEqual(result['effective_deadline'],81138.171)
        self.assertTrue(result['accepted']);self.assertEqual(len(result['deadline_shortenings']),1)
    def test_palette_closes_after_two_verified_frames_keeps_history_only(self):
        io=RecordedGoalIO()
        def planner(*args,**kw):
            io.failure=ValueError('Active palette session changed')
            return dict(candidate=None,compromise_candidate=None,effective_deadline=kw['engineering_deadline'],
                result_classification='not_found_in_budget')
        rules=[dict(enabled=True,exact=True,colors=['#000000'],tolerance=0.) for _ in range(3)]
        result=run_goal_loop(io,io.session,io.settings,rules,engineering_deadline=io.end,
            clock=io.clock,planner=planner,pause=io.pause,retry_requested=lambda:False)
        self.assertFalse(result['accepted']);self.assertFalse(result['verified'])
        self.assertEqual(result['actual_colors'],[None,None,None])
        self.assertEqual(result.get('last_verified_colors'),['#389B8D','#10AECE','#675140'])
        self.assertTrue(result.get('last_verified_screenshot'))
        self.assertEqual(result.get('last_verified_captured_monotonic'),81094.171)
        self.assertNotEqual(result['outcome'],'matched')
        self.assertEqual(io.released,1)
    def test_typed_palette_stop_clears_a_cached_match_and_reports_normal_stop(self):
        from native_live.session_status import PaletteEnded
        io=RecordedGoalIO()
        rules=[dict(enabled=True,exact=True,colors=[color],tolerance=0.) for color in io.current['checkpoint']['client_hex']]
        def event(row):
            if row['event']=='native_retry_available':
                io.failure=PaletteEnded('No longer active',dict(stop_reason='palette_ended',classification='normal_stop',changed_fields=['active']))
        result=run_goal_loop(io,io.session,io.settings,rules,engineering_deadline=io.end,
            clock=io.clock,pause=io.pause,retry_requested=lambda:False,event=event)
        self.assertEqual(result['stop_reason'],'palette_ended')
        self.assertEqual(result['session_stop_classification'],'normal_stop')
        self.assertEqual(result['actual_colors'],[None,None,None]);self.assertFalse(result['accepted'])
        self.assertTrue(result['last_verified_screenshot'])
        self.assertEqual(result['last_verified_colors'],['#389B8D','#10AECE','#675140'])
        self.assertEqual(result['outcome'],'stopped')
    def test_native_filled_color_omission_cannot_become_screenshot_history(self):
        io=RecordedGoalIO()
        for frame in io.current['frames']:
            frame['screenshot_hex'][1]=None;frame['hex_source'][1]='native_checkpoint'
            frame['screenshot_hex_verified']=False
        rules=[dict(enabled=True,exact=True,colors=['#000000'],tolerance=0.) for _ in range(3)]
        result=run_goal_loop(io,io.session,io.settings,rules,engineering_deadline=io.end,
            clock=io.clock,planner=lambda *a,**kw:(_ for _ in ()).throw(ValueError('forced local stop')))
        self.assertFalse(result.get('last_verified_screenshot',False))
        self.assertIsNone(result.get('last_verified_colors'))
    def test_persistent_local_frame_timeout_keeps_native_read_separate_from_current_actual(self):
        io=RecordedGoalIO()
        rules=[dict(enabled=True,exact=True,colors=['#000000'],tolerance=0.) for _ in range(3)]
        io.frames=lambda *args:(_ for _ in ()).throw(TimeoutError('decoder local deadline'))
        result=run_goal_loop(io,io.session,io.settings,rules,engineering_deadline=io.end,
            clock=io.clock,pause=io.pause)
        self.assertFalse(result['accepted']);self.assertFalse(result['verified'])
        self.assertEqual(result['actual_colors'],[None,None,None])
        self.assertEqual(result['native_current']['checkpoint']['client_hex'],['#389B8D','#10AECE','#675140'])
        self.assertFalse(result['screenshot_verified'])
    def test_generic_stop_after_verified_initial_keeps_history_without_current_match(self):
        for error,reason in ((InterruptedError('F9'),'interrupted'),
                (TimeoutError('session deadline'),'insufficient_time'),
                (OSError('process unavailable'),'observation_failed'),
                (ValueError('invalid live read'),'observation_failed'),
                (RuntimeError('capture unavailable'),'observation_failed'),
                (KeyError('missing live data'),'observation_failed')):
            with self.subTest(error=type(error).__name__):
                io=RecordedGoalIO()
                rules=[dict(enabled=True,exact=True,colors=[c],tolerance=0.) for c in io.current['checkpoint']['client_hex']]
                def event(row):
                    if row['event']=='native_retry_available' and row['reason']=='searching':raise error
                result=run_goal_loop(io,io.session,io.settings,rules,engineering_deadline=io.end,
                    clock=io.clock,pause=io.pause,retry_requested=lambda:False,event=event)
                self.assertEqual(result['stop_reason'],reason,result.get('error'));self.assertFalse(result['verified'])
                self.assertFalse(result['accepted']);self.assertIsNone(result['current'])
                self.assertEqual(result['actual_colors'],[None,None,None])
                self.assertEqual(result['outcome'],'stopped');self.assertTrue(result['last_verified_screenshot'])
                self.assertEqual(io.released,1)
    def test_unknown_input_goal_stop_cannot_reaccept_a_cached_matching_color(self):
        from native_live.controller import GoalStop
        io=RecordedGoalIO()
        rules=[dict(enabled=True,exact=True,colors=[c],tolerance=0.) for c in io.current['checkpoint']['client_hex']]
        def event(row):
            if row['event']=='native_retry_available' and row['reason']=='searching':raise GoalStop('input_outcome_unknown')
        result=run_goal_loop(io,io.session,io.settings,rules,engineering_deadline=io.end,
            clock=io.clock,pause=io.pause,retry_requested=lambda:False,event=event)
        self.assertEqual(result['stop_reason'],'input_outcome_unknown');self.assertFalse(result['verified'])
        self.assertFalse(result['accepted']);self.assertIsNone(result['current'])
        self.assertEqual(result['outcome'],'stopped');self.assertTrue(result['last_verified_screenshot'])
    def test_fresh_final_target_observation_remains_current_and_matched(self):
        io=RecordedGoalIO();rules=[dict(enabled=True,exact=True,colors=[c],tolerance=0.) for c in io.current['checkpoint']['client_hex']]
        result=run_goal_loop(io,io.session,io.settings,rules,engineering_deadline=io.end,clock=io.clock,pause=io.pause)
        self.assertEqual(result['stop_reason'],'target_observed');self.assertTrue(result['verified'])
        self.assertTrue(result['accepted']);self.assertIsNotNone(result['current'])
    def test_release_failure_clears_current_match_and_keeps_screenshot_history(self):
        io=RecordedGoalIO()
        io.release=lambda:(_ for _ in ()).throw(OSError('mouse release failed'))
        rules=[dict(enabled=True,exact=True,colors=[c],tolerance=0.) for c in io.current['checkpoint']['client_hex']]
        result=run_goal_loop(io,io.session,io.settings,rules,engineering_deadline=io.end,clock=io.clock,pause=io.pause)
        self.assertEqual(result['release_error'],'mouse release failed');self.assertFalse(result['verified'])
        self.assertFalse(result['accepted']);self.assertIsNone(result['current'])
        self.assertEqual(result['outcome'],'stopped');self.assertTrue(result['last_verified_screenshot'])
    def test_unconfirmed_visual_goal_stop_does_not_promote_native_filled_frame(self):
        from native_live.controller import GoalStop
        io=RecordedGoalIO()
        for frame in io.current['frames']:
            frame['screenshot_hex'][1]=None;frame['hex_source'][1]='native_checkpoint';frame['screenshot_hex_verified']=False
        rules=[dict(enabled=True,exact=True,colors=[c],tolerance=0.) for c in io.current['checkpoint']['client_hex']]
        def event(row):
            if row['event']=='native_retry_available' and row['reason']=='searching':raise GoalStop('target_visual_unconfirmed')
        result=run_goal_loop(io,io.session,io.settings,rules,engineering_deadline=io.end,
            clock=io.clock,pause=io.pause,retry_requested=lambda:False,event=event)
        self.assertEqual(result['stop_reason'],'target_visual_unconfirmed');self.assertFalse(result['verified'])
        self.assertFalse(result['accepted']);self.assertIsNone(result['current'])
        self.assertEqual(result['outcome'],'stopped');self.assertFalse(result.get('last_verified_screenshot',False))
    def test_normal_budget_stop_preserves_a_complete_actual_screenshot_read(self):
        from native_live.controller import GoalStop
        io=RecordedGoalIO()
        rules=[dict(enabled=True,exact=True,colors=['#000000'],tolerance=0.) for _ in range(3)]
        def planner(*args,**kw):raise GoalStop('not_found_in_budget')
        result=run_goal_loop(io,io.session,io.settings,rules,engineering_deadline=io.end,
            clock=io.clock,pause=io.pause,planner=planner)
        self.assertEqual(result['stop_reason'],'not_found_in_budget');self.assertTrue(result['verified'])
        self.assertFalse(result['accepted']);self.assertIsNotNone(result['current'])
        self.assertEqual(result['actual_colors'],['#389B8D','#10AECE','#675140'])


if __name__=='__main__':unittest.main()
