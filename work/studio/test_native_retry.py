"""Same-session retry with a tiny offline palette and actual input replay."""
import copy
from dataclasses import asdict
import importlib.util
import inspect
import json
import unittest

import numpy as np

from input_gestures import PointerGesture,drag_gesture
from native_input_response import InputGeometry, InputSettings, replay_native_route
from native_input_route_search import _needed
from native_palette_scoring import score_native_pose
from native_live.controller import run_goal_loop
from native_live.same_session_dye_planner import audit_candidate_endpoint,_plan_fingerprint


class RetryIO:
    def __init__(self,count=3,scale=1.):
        self.t=1.;self.actions=[];self.releases=0;self.labels=[];self.cancel=False
        self.settings=InputSettings(.5,3.,0.,.1,.01)
        pixels=np.zeros((254,254,3),dtype=np.uint8)
        pixels[:,:,0]=np.arange(254,dtype=np.uint8)[None,:]
        pixels[:,:,1]=np.arange(254,dtype=np.uint8)[:,None]
        pixels[:,:,2]=75
        self.pose=dict(position=[0.,0.],scale=scale,rotation_degrees=0.)
        self.session=dict(pixels=tuple(pixels.copy() for _ in range(count)),
            picker_uv=[[(i+.5)/count,.4+i*.05] for i in range(count)],
            color_preserve_ratio=0.,initial_pose=copy.deepcopy(self.pose),capture_id='offline-retry',region_count=count)
        self.geometry=InputGeometry([10.,10.,510.,510.],[500.,500.],'windows_legacy_mouse_pixels')
        self.binding=json.dumps([['same-round'],[123,'offline-process'],{},asdict(self.settings),{}])
        self.neutral=[dict(enabled=True,exact=True,colors=['#000000'],tolerance=0.) for _ in range(count)]
        self.rules=[dict(enabled=True,exact=True,colors=[c],tolerance=0.) for c in self.colors()]
        self.interrupt_action=False;self.unknown_input=False;self.stuck_wheel=False
    def clock(self):return self.t
    def pause(self,seconds):self.t+=seconds
    def check(self,deadline):
        if self.cancel:raise InterruptedError('F9')
        if self.t>=deadline:raise TimeoutError('deadline')
    planning_check=check
    def input_backend(self,deadline):
        self.check(deadline)
        return dict(process_identity=[123,'offline-process'],backend_object='offline',
            backend_type='MM.Client.Framework.InputSystem.InputManager',input_assistant='0x0',
            legacy_mouse_getter_rva='0x185310',viewport_origin=[0,0],viewport_scale=[1.,1.])
    def colors(self):return score_native_pose(self.session,self.pose,self.neutral)['colors']
    def checkpoint(self,label,deadline):
        self.check(deadline);self.t+=.02;self.labels.append(label)
        return dict(checkpoint_valid=True,cpu_matches=True,label=label,binding=self.binding,
            board=list(self.geometry.board),local_size=list(self.geometry.local_size),
            pose=copy.deepcopy(self.pose),client_hex=self.colors())
    def frames(self,label,deadline):
        self.check(deadline);self.t+=.04
        return [dict(hex=self.colors(),remaining_seconds=None,captured_monotonic=self.t+offset) for offset in (-.01,0.)]
    def perform_candidate(self,record,label,deadline):
        self.check(deadline);self.actions.append(copy.deepcopy(record));self.t+=record['input_seconds']+.1
        if not self.stuck_wheel:
            self.pose=replay_native_route(self.pose,[record],self.geometry,self.settings,
                wheel_delta_per_step=1.,sample_policy='all_recorded_points')['final_pose']
        return dict(completed=not self.unknown_input,released=True,gesture=record,
            actual_trace=[dict(actual_client=list(p)) for p in record['points']])
    def release(self):self.releases+=1


class NativeRetryTests(unittest.TestCase):
    def run_loop(self,io,requested,event,**kwargs):
        self.assertIn('retry_requested',inspect.signature(run_goal_loop).parameters)
        def no_route(context,cp,frames,rules,grid,**kw):
            self.assertNotIn('collect_candidates',kw)
            return dict(candidate=None,compromise_candidate=None,effective_deadline=kw['engineering_deadline'],
                result_classification='not_found_in_budget')
        return run_goal_loop(io,io.session,io.settings,io.rules,engineering_deadline=kwargs.pop('deadline',90.),
            clock=io.clock,pause=io.pause,retry_requested=requested,event=event,planner=kwargs.pop('planner',no_route),**kwargs)
    def once_ready(self,io,*,retry_at=None):
        pending=[False];sent=[False];events=[]
        def event(row):
            events.append(row)
            if row['event']=='native_retry_available' and row.get('reason')=='target_observed' and not sent[0]:
                sent[0]=True;pending[0]=True
                if retry_at is not None:io.t=retry_at
        def requested():
            value=pending[0];pending[0]=False;return value
        return requested,event,events
    def test_retry_zooms_to_verified_minimum_and_keeps_deadline_and_grace(self):
        for count in (2,3):
            with self.subTest(count=count):
                io=RetryIO(count);requested,event,events=self.once_ready(io,retry_at=34.)
                result=self.run_loop(io,requested,event)
                self.assertEqual(result['retry_epochs'],1)
                self.assertEqual(result['effective_deadline'],90.)
                self.assertEqual(io.timer_grace_until,31.)
                self.assertEqual(io.pose['scale'],float(np.float32(io.settings.minimum_scale)))
                self.assertGreater(len(io.actions),1)
                self.assertTrue(all(row['kind']=='wheel' and -32<=row['wheel_steps']<0 for row in io.actions))
                self.assertEqual(io.releases,1)
                self.assertIn('retry_1_after',io.labels)
                self.assertEqual(result['best_actual_colors'],io.colors())
                self.assertFalse(result.get('restoration_rounds'))
                self.assertTrue(any(row['event']=='native_retry_reset' and row['status']=='searching' for row in events))
    def test_retry_without_minimum_search_budget_preserves_current_without_input(self):
        io=RetryIO();requested,event,events=self.once_ready(io,retry_at=66.)
        result=self.run_loop(io,requested,event)
        self.assertEqual(io.actions,[])
        self.assertTrue(result['accepted'])
        self.assertEqual(result['stop_reason'],'target_observed')
        self.assertTrue(any(row['event']=='native_retry_reset' and row['status']=='rejected'
            and row['reason']=='insufficient_retry_time' for row in events))
    def test_recorded_fifty_second_retry_runs_reset_and_useful_bounded_search(self):
        io=RetryIO(scale=1.3716416358947754)
        checkpoint=io.checkpoint;frames=io.frames;perform=io.perform_candidate
        def measured_checkpoint(label,deadline):
            io.t+=1.073;return checkpoint(label,deadline)
        def measured_frames(label,deadline):
            io.t+=2.898;return frames(label,deadline)
        def measured_perform(record,label,deadline):
            io.t+=.219;return perform(record,label,deadline)
        io.checkpoint=measured_checkpoint;io.frames=measured_frames;io.perform_candidate=measured_perform
        requested,event,events=self.once_ready(io,retry_at=41.406)
        plans=[]
        def planner(context,cp,frames,rules,grid,**kw):
            plans.append(dict(pose=copy.deepcopy(cp['pose']),budget=kw['time_budget_seconds']))
            return dict(candidate=None,compromise_candidate=None,effective_deadline=kw['engineering_deadline'],
                result_classification='not_found_in_budget')
        result=self.run_loop(io,requested,event,planner=planner)
        self.assertEqual(result['retry_epochs'],1)
        self.assertEqual([row['wheel_steps'] for row in io.actions],[-32,-32,-32,-5])
        self.assertEqual(len(plans),1)
        self.assertEqual(plans[0]['pose']['scale'],float(np.float32(.5)))
        self.assertGreaterEqual(plans[0]['budget'],5.)
        self.assertLessEqual(plans[0]['budget'],25.)
        checks=result['retry_budget_checks']
        after=next(row for row in checks if row['phase']=='after_reference')
        self.assertTrue(after['enabled']);self.assertEqual(after['reference_allowance_seconds'],0.)
        self.assertEqual(after['reset_actions'],4)
        self.assertAlmostEqual(after['remaining_seconds'],47.501,places=3)
        self.assertAlmostEqual(after['visual_allowance_seconds'],6.5465,places=4)
        self.assertEqual(after['minimum_search_seconds'],5.)
        self.assertEqual(after['closing_guard_seconds'],8.25)
    def test_retry_button_and_admission_use_complete_reset_route_cost(self):
        io=RetryIO();pending=[False];events=[];requested_once=[False]
        def event(row):
            events.append(row)
            if row['event']=='observed' and not requested_once[0]:
                io.t=65.;pending[0]=True;requested_once[0]=True
        def requested():
            value=pending[0];pending[0]=False;return value
        result=self.run_loop(io,requested,event)
        self.assertEqual(io.actions,[])
        availability=next(row for row in events if row['event']=='native_retry_available'
            and row.get('waiting_for_retry'))
        self.assertFalse(availability['enabled'])
        self.assertEqual(availability['reason'],'insufficient_retry_time')
        self.assertEqual(availability['budget']['reset_actions'],3)
        self.assertTrue(any(row['phase']=='before_reference' and not row['enabled']
            for row in result['retry_budget_checks']))
    def test_retry_action_quota_reserves_only_reset_and_one_usable_target_action(self):
        for quota,expected in ((3,0),(4,1)):
            with self.subTest(quota=quota):
                io=RetryIO();pending=[False];sent=[False];events=[]
                def event(row):
                    events.append(row)
                    if row['event']=='observed' and not sent[0]:pending[0]=True;sent[0]=True
                def requested():
                    value=pending[0];pending[0]=False;return value
                result=self.run_loop(io,requested,event,max_actions=quota)
                self.assertEqual(result['retry_epochs'],expected)
                self.assertEqual(len(io.actions),3 if expected else 0)
                availability=next(row for row in events if row['event']=='native_retry_available'
                    and row.get('waiting_for_retry'))
                self.assertEqual(availability['enabled'],bool(expected))
                self.assertEqual(availability['budget']['required_actions'],4)
    def test_already_minimum_retry_can_research_without_fake_reset_gestures(self):
        io=RetryIO(scale=.5);requested,event,events=self.once_ready(io,retry_at=70.)
        result=self.run_loop(io,requested,event)
        self.assertEqual(result['retry_epochs'],1)
        self.assertEqual(io.actions,[])
        after=next(row for row in result['retry_budget_checks'] if row['phase']=='after_reference')
        self.assertEqual(after['reset_actions'],0)
        self.assertEqual(after['reset_allowance_seconds'],0.)
        self.assertEqual(after['required_seconds'],17.25)
    def test_fresh_reference_can_reject_slow_reset_without_sending_wheels(self):
        io=RetryIO();requested,event,events=self.once_ready(io,retry_at=34.)
        checkpoint=io.checkpoint
        def slow_reference(label,deadline):
            if label=='retry_1_reference':io.t+=12.
            return checkpoint(label,deadline)
        io.checkpoint=slow_reference
        result=self.run_loop(io,requested,event)
        self.assertEqual(io.actions,[])
        before=next(row for row in result['retry_budget_checks'] if row['phase']=='before_reference')
        after=next(row for row in result['retry_budget_checks'] if row['phase']=='after_reference')
        self.assertTrue(before['enabled']);self.assertFalse(after['enabled'])
        self.assertEqual(after['reason'],'insufficient_retry_time')
        self.assertEqual(after['reference_allowance_seconds'],0.)
        self.assertTrue(result['accepted'])
    def test_exhausted_post_reset_search_budget_never_runs_tiny_fake_search(self):
        io=RetryIO();requested,original_event,events=self.once_ready(io);plans=[]
        def event(row):
            original_event(row)
            if row['event']=='native_retry_reset' and row.get('status')=='searching':io.t=77.75
        def planner(*args,**kw):
            plans.append(kw)
            return dict(candidate=None,compromise_candidate=None,effective_deadline=kw['engineering_deadline'],
                result_classification='not_found_in_budget')
        result=self.run_loop(io,requested,event,planner=planner)
        self.assertEqual(result['retry_epochs'],1)
        self.assertEqual(plans,[])
        self.assertEqual(result['stop_reason'],'insufficient_time')
        search=next(row for row in result['retry_budget_checks'] if row['phase']=='search')
        self.assertFalse(search['enabled']);self.assertEqual(search['search_cap_seconds'],0.)
    def test_minimum_scale_late_retry_still_receives_five_seconds_of_search(self):
        io=RetryIO(scale=.5);requested,original_event,events=self.once_ready(io,retry_at=70.);plans=[];moved=[False]
        def event(row):
            original_event(row)
            if row['event']=='native_retry_available' and row.get('reason')=='target_observed' and not moved[0]:
                io.pose['position'][0]=.02;moved[0]=True
        def planner(*args,**kw):
            plans.append(kw['time_budget_seconds'])
            return dict(candidate=None,compromise_candidate=None,effective_deadline=kw['engineering_deadline'],
                result_classification='not_found_in_budget')
        result=self.run_loop(io,requested,event,planner=planner)
        self.assertEqual(result['retry_epochs'],1)
        self.assertEqual(io.actions,[])
        self.assertEqual(len(plans),1)
        self.assertGreaterEqual(plans[0],5.)
    def test_retry_search_does_not_authorize_an_actual_route_over_time_or_action_budget(self):
        from native_live.retry import minimum_scale_route
        for limit in ('time','actions'):
            with self.subTest(limit=limit):
                io=RetryIO();events=[];pending=[False];sent=[False];plans=[]
                reset=minimum_scale_route(io.pose,io.geometry,io.settings)
                anchor=replay_native_route(io.pose,reset,io.geometry,io.settings,
                    wheel_delta_per_step=1.,sample_policy='all_recorded_points')['final_pose']
                route=[drag_gesture(io.geometry.board,30,0).record(),drag_gesture(io.geometry.board,0,20).record()]
                endpoint=replay_native_route(anchor,route,io.geometry,io.settings,
                    wheel_delta_per_step=1.,sample_policy='all_recorded_points')['final_pose']
                colors=score_native_pose(io.session,endpoint,io.neutral)['colors']
                io.rules=[dict(enabled=True,exact=True,colors=[c],tolerance=0.) for c in colors]
                def event(row):
                    events.append(row)
                    if row['event']=='native_retry_available' and row.get('reason')=='not_found_in_budget' and not sent[0]:
                        pending[0]=True;sent[0]=True
                def requested():
                    value=pending[0];pending[0]=False;return value
                def planner(context,cp,frames,rules,grid,**kw):
                    plans.append(copy.deepcopy(cp))
                    if len(plans)==1:
                        return dict(candidate=None,compromise_candidate=None,effective_deadline=kw['engineering_deadline'],
                            result_classification='not_found_in_budget')
                    row=audit_candidate_endpoint(context,cp,rules,dict(input_route=route,final_pose=endpoint,
                        prediction=score_native_pose(io.session,endpoint,rules),needed=_needed(route,3.,.5)))
                    plan=dict(schema=1,context_fingerprint=context['fingerprint'],reference_pose=cp['pose'],
                        reference_frame_monotonic=frames[-1]['captured_monotonic'],planned_at=io.clock(),
                        effective_deadline=kw['engineering_deadline'],candidate=row,
                        reserve_seconds=10.,verification_margin_seconds=8.)
                    plan['plan_fingerprint']=_plan_fingerprint(plan)
                    if limit=='time':io.t=kw['engineering_deadline']-10.
                    return plan
                result=self.run_loop(io,requested,event,planner=planner,max_actions=4 if limit=='actions' else 64)
                self.assertEqual(result['retry_epochs'],1)
                self.assertEqual(len(plans),2)
                self.assertEqual(len(io.actions),len(reset))
                self.assertTrue(all(row['kind']=='wheel' for row in io.actions))
                self.assertEqual(result['stop_reason'],'insufficient_time' if limit=='time' else 'insufficient_route_actions',result.get('error'))
    def test_f9_during_reset_stops_before_the_next_wheel_group(self):
        io=RetryIO();requested,event,events=self.once_ready(io);perform=io.perform_candidate
        def cancel_after_first_wheel(*args):
            receipt=perform(*args);io.cancel=True;return receipt
        io.perform_candidate=cancel_after_first_wheel
        result=self.run_loop(io,requested,event)
        self.assertEqual(result['stop_reason'],'interrupted')
        self.assertEqual(len(io.actions),1)
        self.assertEqual(result['retry_epochs'],0)
        self.assertEqual(io.releases,1)
    def test_unsupported_zoom_rejects_retry_without_input_or_new_search(self):
        io=RetryIO();io.settings=InputSettings(.5,3.,0.,.1,0.)
        binding=json.loads(io.binding);binding[3]=asdict(io.settings);io.binding=json.dumps(binding)
        pending=[False];sent=[False];events=[]
        def event(row):
            events.append(row)
            if row['event']=='observed' and not sent[0]:pending[0]=True;sent[0]=True
        def requested():
            value=pending[0];pending[0]=False;return value
        result=self.run_loop(io,requested,event)
        self.assertEqual(io.actions,[]);self.assertTrue(result['accepted'])
        self.assertTrue(any(row['event']=='native_retry_reset' and row['status']=='rejected'
            and row['reason']=='unsupported_retry_settings' for row in events))
    def test_wait_closes_with_fresh_actual_read_and_keeps_matched_outcome(self):
        io=RetryIO();events=[]
        result=self.run_loop(io,lambda:False,events.append)
        self.assertEqual(io.actions,[])
        self.assertTrue(result['accepted']);self.assertEqual(result['stop_reason'],'target_observed')
        self.assertIn('retry_wait_closed',io.labels)
        self.assertLess(io.t,90.-8.)
        self.assertTrue(any(row['event']=='native_retry_available' and
            row.get('reason')=='insufficient_retry_time' and row.get('enabled') is False for row in events))
    def test_wait_final_read_reports_a_user_changed_board_from_actual_pose(self):
        io=RetryIO();before=io.colors();original=io.pause;changed=[False]
        def pause(seconds):
            original(seconds)
            if io.t>35. and not changed[0]:
                io.pose['position'][0]=.02;changed[0]=True
        io.pause=pause
        result=self.run_loop(io,lambda:False,lambda row:None)
        self.assertNotEqual(result['actual_colors'],before)
        self.assertEqual(result['actual_colors'],io.colors())
        self.assertFalse(result['accepted']);self.assertEqual(result['stop_reason'],'compromise_observed')
    def test_wait_without_final_read_clears_cached_match(self):
        io=RetryIO();original=io.check
        def check(deadline):
            original(deadline)
            if io.t>75. and io.t<82.:
                io.pose['position'][0]=.02;io.t+=10.
        io.check=check
        result=self.run_loop(io,lambda:False,lambda row:None)
        self.assertFalse(result['accepted']);self.assertFalse(result['verified'])
        self.assertEqual(result['stop_reason'],'insufficient_time')
        self.assertIsNone(result['current']);self.assertIn('last_verified_retry',result)
    def test_retry_does_not_restart_late_timer_grace_or_restore_deadline(self):
        io=RetryIO();requested,event,events=self.once_ready(io,retry_at=34.)
        original=io.frames
        def frames(label,deadline):
            rows=original(label,deadline)
            if label=='retry_1_after':
                for row in rows:row['remaining_seconds']=30
            return rows
        io.frames=frames
        result=self.run_loop(io,requested,event)
        self.assertLess(result['effective_deadline'],90.)
        self.assertEqual(io.timer_grace_until,31.)
        retry_observation=next(row for row in result['observations'] if row['label']=='retry_1_after')
        self.assertTrue(any(row['timer_policy']=='consistent_pair_shortened_deadline' for row in retry_observation['frames']))
    def test_unconfirmed_wheel_minimum_never_starts_new_search(self):
        io=RetryIO();io.stuck_wheel=True;requested,event,events=self.once_ready(io)
        result=self.run_loop(io,requested,event)
        self.assertEqual(result['planning_rounds'],[])
        self.assertEqual(result['stop_reason'],'retry_minimum_unconfirmed')
        self.assertLessEqual(len(io.actions),4)
        self.assertFalse(any(row['event']=='native_retry_reset' and row['status']=='searching' for row in events))
    def test_unknown_input_outcome_does_not_begin_retry_search(self):
        io=RetryIO();io.unknown_input=True;requested,event,events=self.once_ready(io)
        result=self.run_loop(io,requested,event)
        self.assertEqual(result['stop_reason'],'input_outcome_unknown')
        self.assertEqual(len(io.actions),1)
        self.assertEqual(result['retry_epochs'],0)
    def test_multiple_retry_epochs_share_global_action_limit(self):
        io=RetryIO();pending=[False];sent=[0]
        def event(row):
            if row['event']=='native_retry_available' and row.get('enabled') and sent[0]<2:
                if row.get('reason') in ('target_observed','not_found_in_budget'):
                    pending[0]=True;sent[0]+=1
        def requested():
            value=pending[0];pending[0]=False;return value
        result=self.run_loop(io,requested,event,max_actions=6)
        self.assertEqual(result['retry_epochs'],2)
        self.assertLessEqual(result['actual_input_attempts'],6)
        self.assertEqual(io.releases,1)

    def test_retry_during_planning_abandons_plan_without_sending_its_input(self):
        io=RetryIO();io.rules[0]['colors']=['#000000'];pending=[False];plans=[]
        def planner(context,cp,frames,rules,grid,**kw):
            plans.append(copy.deepcopy(cp))
            if len(plans)==1:
                pending[0]=True;kw['check']()
            self.assertEqual(kw['time_budget_seconds'],25.)
            return dict(candidate=None,compromise_candidate=None,effective_deadline=kw['engineering_deadline'],
                result_classification='not_found_in_budget')
        def requested():
            value=pending[0];pending[0]=False;return value
        result=self.run_loop(io,requested,lambda row:None,planner=planner)
        self.assertEqual(result['retry_epochs'],1)
        self.assertEqual(len(plans),2)
        self.assertEqual(plans[1]['pose']['scale'],.5)
        self.assertTrue(all(row['kind']=='wheel' for row in io.actions))
    def test_partial_released_gesture_is_counted_once_then_retry_reads_actual_pose(self):
        from native_live.retry import RetryRequested
        io=RetryIO();pending=[False];plans=[];events=[]
        gesture=PointerGesture('drag',((260,260),(270,260))).record()
        endpoint=replay_native_route(io.pose,[gesture],io.geometry,io.settings,
            wheel_delta_per_step=1.,sample_policy='all_recorded_points')['final_pose']
        colors=score_native_pose(io.session,endpoint,io.neutral)['colors']
        io.rules=[dict(enabled=True,exact=True,colors=[c],tolerance=0.) for c in colors]
        def planner(context,cp,frames,rules,grid,**kw):
            plans.append(copy.deepcopy(cp))
            if len(plans)>1:
                return dict(candidate=None,compromise_candidate=None,effective_deadline=kw['engineering_deadline'],
                    result_classification='not_found_in_budget')
            row=audit_candidate_endpoint(context,cp,rules,dict(input_route=[gesture],final_pose=endpoint,
                prediction=score_native_pose(io.session,endpoint,rules),needed=_needed([gesture],3.,.5)))
            plan=dict(schema=1,context_fingerprint=context['fingerprint'],reference_pose=cp['pose'],
                reference_frame_monotonic=frames[-1]['captured_monotonic'],planned_at=io.clock(),
                effective_deadline=kw['engineering_deadline'],candidate=row,
                reserve_seconds=10.,verification_margin_seconds=8.)
            plan['plan_fingerprint']=_plan_fingerprint(plan);return plan
        original=io.perform_candidate
        def perform(record,label,deadline):
            if record['kind']=='drag':
                partial=PointerGesture('drag',((260,260),(264,260))).record()
                receipt=original(partial,label,deadline)
                receipt.update(completed=False,interrupted=True,released=True)
                error=RetryRequested('F7');error.receipt=receipt;raise error
            return original(record,label,deadline)
        io.perform_candidate=perform
        result=self.run_loop(io,lambda:False,events.append,planner=planner)
        self.assertEqual(result['retry_epochs'],1)
        self.assertEqual(result['actual_input_attempts'],len(io.actions))
        self.assertEqual(sum(row['kind']=='drag' for row in io.actions),1)
        self.assertTrue(result['steps'][0]['receipt']['released'])
        reference=next(row for row in result['observations'] if row['label']=='retry_1_reference')
        self.assertNotEqual(reference['checkpoint']['pose'],result['initial']['checkpoint']['pose'])
        self.assertEqual(io.releases,1)
    def test_retry_reset_coalesces_repeated_press_without_another_epoch(self):
        io=RetryIO();requested,event,events=self.once_ready(io)
        original=io.perform_candidate
        def perform(record,label,deadline):
            # The installed runtime check remains active, but is suppressed
            # while the reset is deliberately executing its bounded route.
            io.retry_check()
            return original(record,label,deadline)
        io.perform_candidate=perform
        result=self.run_loop(io,requested,event)
        self.assertEqual(result['retry_epochs'],1)
        self.assertEqual(sum(row['status']=='searching' for row in result['retries']),1)
    def test_f9_during_wait_does_not_run_retry_wheels(self):
        io=RetryIO();events=[]
        def event(row):
            events.append(row)
            if row['event']=='native_retry_available' and row.get('reason')=='target_observed':io.cancel=True
        result=self.run_loop(io,lambda:False,event)
        self.assertEqual(result['stop_reason'],'interrupted')
        self.assertEqual(io.actions,[]);self.assertEqual(io.releases,1)
        self.assertFalse(result['accepted'])
    def test_retry_without_a_receipt_is_unknown_and_never_starts_reset(self):
        from native_live.retry import RetryRequested
        io=RetryIO();requested,event,events=self.once_ready(io)
        def unknown(*args):raise RetryRequested('partial input without receipt')
        io.perform_candidate=unknown
        result=self.run_loop(io,requested,event)
        self.assertEqual(result['stop_reason'],'input_outcome_unknown')
        self.assertEqual(result['retry_epochs'],0)
        self.assertEqual(result['actual_input_attempts'],1)
    def test_failed_mouse_release_never_sends_next_reset_group(self):
        io=RetryIO();requested,event,events=self.once_ready(io)
        original=io.perform_candidate
        def unreleased(*args):
            receipt=original(*args);receipt['released']=False;return receipt
        io.perform_candidate=unreleased
        result=self.run_loop(io,requested,event)
        self.assertEqual(result['stop_reason'],'input_outcome_unknown')
        self.assertEqual(len(io.actions),1)
        self.assertEqual(result['retry_epochs'],0)
    def test_slow_initial_visual_reserves_actual_final_read_cost(self):
        io=RetryIO();original=io.frames
        def frames(label,deadline):
            io.t+=7.;return original(label,deadline)
        io.frames=frames
        result=self.run_loop(io,lambda:False,lambda row:None)
        self.assertTrue(result['accepted'])
        self.assertIn('retry_wait_closed',io.labels)
        self.assertLess(io.t,90.-8.)
    def test_retry_keeps_mixed_priorities_alternatives_and_disabled_region(self):
        io=RetryIO();io.rules[0].update(exact=False,tolerance=8.,priority=1,
            colors=[io.rules[0]['colors'][0],'#FEFEFE'])
        io.rules[1].update(priority=2)
        io.rules[2].update(enabled=False,colors=[],priority=3)
        requested,event,events=self.once_ready(io)
        result=self.run_loop(io,requested,event)
        self.assertEqual(result['rules'][0]['priority'],1)
        self.assertEqual(set(result['rules'][0]['colors']),set(io.rules[0]['colors']))
        self.assertEqual(result['rules'][0]['tolerance'],8.)
        self.assertFalse(result['rules'][2]['enabled'])


class RetryMinimumRouteTests(unittest.TestCase):
    def test_recorded_budget_charges_reference_only_before_its_actual_read(self):
        from native_live.retry import retry_budget
        io=RetryIO(scale=1.3716416358947754)
        from native_live.retry import minimum_scale_route
        route=minimum_scale_route(io.pose,io.geometry,io.settings)
        costs=dict(native=[1.093],closing_visual=[4.031],input=[.319])
        before=retry_budget(route,costs,include_reference=True)
        after=retry_budget(route,costs,include_reference=False)
        self.assertAlmostEqual(before['required_seconds'],34.626,places=4)
        self.assertAlmostEqual(after['required_seconds'],32.6865,places=4)
        self.assertAlmostEqual(before['reset_input_seconds'],2.218,places=4)
        self.assertAlmostEqual(before['native_allowance_seconds'],1.9395,places=4)
        self.assertAlmostEqual(before['input_preparation_allowance_seconds'],.7285,places=4)
        self.assertEqual(before['required_actions'],5)
    def test_minimum_route_uses_complete_native_float_replay_and_bounded_groups(self):
        self.assertIsNotNone(importlib.util.find_spec('native_live.retry'))
        from native_live.retry import minimum_scale_route
        io=RetryIO(scale=3.)
        route=minimum_scale_route(io.pose,io.geometry,io.settings)
        self.assertTrue(route)
        self.assertTrue(all(-32<=g['wheel_steps']<0 for g in route))
        after=replay_native_route(io.pose,route,io.geometry,io.settings,
            wheel_delta_per_step=1.,sample_policy='all_recorded_points')['final_pose']
        self.assertEqual(after['scale'],float(np.float32(io.settings.minimum_scale)))
        prior=replay_native_route(io.pose,[*route[:-1],PointerGesture('wheel',route[-1]['points'],
            wheel_steps=route[-1]['wheel_steps']+1).record()],io.geometry,io.settings,
            wheel_delta_per_step=1.,sample_policy='all_recorded_points')['final_pose']
        self.assertGreater(prior['scale'],after['scale'])


class RetryInputBoundaryTests(unittest.TestCase):
    def setUp(self):
        from test_native_protected_io import NativeProtectedIOTests
        self.fixture=NativeProtectedIOTests();self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.io=self.fixture.io;self.game=self.fixture.game;self.releases=[]
        self.game.send=self.releases.append
    def test_partial_retry_attaches_released_real_receipt_and_counts_once(self):
        from native_live.retry import RetryRequested
        def interrupted(gesture):
            self.game.inputs.append(gesture.record())
            self.game.last_input_trace=[dict(actual_client=list(gesture.points[0]))]
            raise RetryRequested('F7 mid-gesture')
        self.game.perform_gesture=interrupted
        with self.assertRaises(RetryRequested) as raised:self.fixture.protected()
        receipt=raised.exception.receipt
        self.assertTrue(receipt['interrupted']);self.assertTrue(receipt['released'])
        self.assertFalse(receipt['completed']);self.assertEqual(self.io.input_attempts,1)
        self.assertEqual(self.releases,[4,16])
        saved=json.loads((self.io.folder/'protected.input.json').read_text())
        self.assertEqual(saved,json.loads(json.dumps(receipt)))
    def test_release_failure_records_unknown_without_claiming_released(self):
        from native_live.retry import RetryRequested
        def interrupted(gesture):raise RetryRequested('F7')
        def failing_release(flag):raise RuntimeError('SendInput rejected release')
        self.game.perform_gesture=interrupted;self.game.send=failing_release
        with self.assertRaises(RetryRequested) as raised:self.fixture.protected()
        self.assertFalse(raised.exception.receipt['released'])
        self.assertIn('release_error',raised.exception.receipt)
    def test_left_release_failure_still_attempts_right_release_and_stays_unknown(self):
        from native_live.retry import RetryRequested
        def interrupted(gesture):raise RetryRequested('F7')
        def release(flag):
            self.releases.append(flag)
            if flag==4:raise RuntimeError('Left release failed')
        self.game.perform_gesture=interrupted;self.game.send=release
        with self.assertRaises(RetryRequested) as raised:self.fixture.protected()
        self.assertEqual(self.releases,[4,16])
        self.assertFalse(raised.exception.receipt['released'])
        self.assertIn('Left release failed',raised.exception.receipt['release_error'])
    def test_final_cleanup_attempts_both_release_buttons_and_reports_failure(self):
        def release(flag):
            self.releases.append(flag)
            if flag==4:raise RuntimeError('Left release failed')
        self.game.send=release;self.io.sent_any=True
        with self.assertRaisesRegex(RuntimeError,'Left release failed'):self.io.release()
        self.assertEqual(self.releases,[4,16])
    def test_retry_before_input_is_explicitly_marked_not_started(self):
        from native_live.retry import RetryRequested
        def requested():raise RetryRequested('F7 before input')
        self.io.retry_check=requested
        with self.assertRaises(RetryRequested) as raised:self.fixture.protected()
        self.assertTrue(getattr(raised.exception,'input_not_started',False))
        self.assertEqual(self.io.input_attempts,0);self.assertEqual(self.game.inputs,[])
    def test_f9_wins_over_retry_request_at_input_guard(self):
        from native_live.retry import RetryRequested
        def requested():raise RetryRequested('F7')
        self.io.retry_check=requested;self.io.f9_pressed=lambda:True
        with self.assertRaises(InterruptedError):self.fixture.protected()
        self.assertEqual(self.game.inputs,[])


if __name__=='__main__':unittest.main()
