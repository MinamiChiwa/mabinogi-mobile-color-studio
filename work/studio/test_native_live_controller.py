"""User rules, actual feedback ownership and hard input limits for native service."""
from test_support import read_local_fixture_text
from test_support import load_local_palette_session
import copy,importlib,importlib.util,json,unittest,time
from pathlib import Path
from native_palette_scoring import load_session,score_native_pose
from native_input_response import InputGeometry,InputSettings,replay_native_route
from test_support import requires_native_case


class FixtureIO:
    def __init__(self):
        fixture=Path(__file__).parent/'fixtures/native_live/stage68'
        requires_native_case(fixture)
        self.case=json.loads(read_local_fixture_text(fixture/'case.json', encoding='utf-8'))
        self.session=load_local_palette_session(fixture/'palette');self.cp=copy.deepcopy(self.case['initial'])
        self.settings=InputSettings(**self.case['settings']);self.pose=copy.deepcopy(self.cp['pose'])
        self.geometry=InputGeometry(self.cp['board'],self.cp['local_size'],'windows_legacy_mouse_pixels')
        self.t=1.;self.actions=[];self.releases=0;self.cancel=False;self.timer=110;self.wrong_pose=False;self.bad_frames=False
        self._clock_at=time.monotonic()
    def clock(self):
        now=time.monotonic();self.t+=now-self._clock_at;self._clock_at=now
        return self.t
    def check(self,deadline):
        if self.cancel:raise InterruptedError('F9')
        if self.t>=deadline:raise TimeoutError('deadline')
    def planning_check(self,deadline):self.check(deadline)
    def input_backend(self,deadline):
        self.check(deadline)
        return dict(process_identity=json.loads(self.cp['binding'])[1],backend_object='archived',
            backend_type='MM.Client.Framework.InputSystem.InputManager',input_assistant='0x0',
            legacy_mouse_getter_rva='0x185310',viewport_origin=[0,0],viewport_scale=[1.,1.])
    def checkpoint(self,label,deadline):
        self.check(deadline);self.t+=.02
        cp=copy.deepcopy(self.cp);cp.update(label=label,pose=copy.deepcopy(self.pose))
        neutral=[dict(enabled=True,exact=True,colors=['#000000'],tolerance=0) for _ in range(3)]
        cp['client_hex']=score_native_pose(self.session,self.pose,neutral)['colors'];return cp
    def frames(self,label,deadline):
        cp=self.checkpoint(label,deadline);self.t+=.02
        frames=[dict(hex=cp['client_hex'],remaining_seconds=self.timer-int(self.t),captured_monotonic=self.t+offset) for offset in (-.01,0.)]
        if self.bad_frames:frames[-1]['hex']=['#000000']*3
        return frames
    def perform_candidate(self,record,label,deadline):
        self.check(deadline);self.actions.append(copy.deepcopy(record));self.t+=.1
        self.pose=replay_native_route(self.pose,[record],self.geometry,self.settings,
            wheel_delta_per_step=1.,sample_policy='all_recorded_points')['final_pose']
        if self.wrong_pose:self.pose['position'][0]+=.001
        return dict(completed=True,input_source='explicit_simulation',gesture=record,
            actual_trace=[dict(actual_client=list(p)) for p in record['points']])
    def release(self):self.releases+=1


class NativeControllerTests(unittest.TestCase):
    def setUp(self):self.io=FixtureIO()
    def run_goal(self,rules=None,**kw):
        self.assertIsNotNone(importlib.util.find_spec('native_live.controller'),'User goal controller missing')
        m=importlib.import_module('native_live.controller')
        return m.run_goal_loop(self.io,self.io.session,self.io.settings,
            self.io.case['rules'] if rules is None else rules,engineering_deadline=kw.pop('engineering_deadline',90.),clock=self.io.clock,**kw)
    def test_startup_visual_readiness_can_recover_after_twenty_seconds(self):
        from native_live.dye_visual_readiness import VisualNotReady
        original=self.io.frames
        def frames(label,deadline):
            if self.io.t<23.:
                self.io.t+=4.;raise VisualNotReady('startup overlay')
            return original(label,deadline)
        self.io.frames=frames
        result=self.run_goal(pause=lambda seconds:setattr(self.io,'t',self.io.t+seconds))
        self.assertTrue(result['accepted']);self.assertGreater(result['elapsed_seconds'],20.)
    def test_startup_per_frame_timeout_is_retryable_but_global_deadline_is_not_extended(self):
        original=self.io.frames;calls=[0]
        def frames(label,deadline):
            calls[0]+=1
            if calls[0]<=2:
                self.io.t+=5.;raise TimeoutError('OCR read deadline expired')
            return original(label,deadline)
        self.io.frames=frames
        result=self.run_goal(pause=lambda seconds:setattr(self.io,'t',self.io.t+seconds))
        self.assertTrue(result['accepted']);self.assertEqual(result['initial_visual_retries'],2)
        self.assertLessEqual(result['effective_deadline'],90.)
    def test_early_missing_and_119_to13_readings_do_not_block_planning(self):
        original=self.io.frames
        def frames(label,deadline):
            rows=original(label,deadline)
            rows[0]['remaining_seconds']=119;rows[1]['remaining_seconds']=13
            return rows
        self.io.frames=frames;result=self.run_goal()
        self.assertTrue(result['accepted']);self.assertEqual(result['effective_deadline'],90.)
    def test_extended_engineering_cap_keeps_thirty_second_timer_grace(self):
        original=self.io.frames
        def frames(label,deadline):
            if label=='initial':self.io.t=21.
            rows=original(label,deadline)
            rows[0]['remaining_seconds']=117;rows[1]['remaining_seconds']=17
            return rows
        self.io.frames=frames
        result=self.run_goal(engineering_deadline=110.)
        self.assertTrue(result['accepted']);self.assertEqual(result['effective_deadline'],110.)
        self.assertTrue(all(frame.get('timer_policy')=='startup_advisory'
            for observation in result['observations'] for frame in observation.get('frames') or []))
    def test_late_unknown_timer_is_advisory_and_a_real_pair_keeps_ten_seconds(self):
        original=self.io.frames;calls=[0]
        # Late reads may shorten the deadline before an old plan is rejected.
        def later(label,deadline):
            if label.endswith('_revalidate') and calls[0]==0:
                calls[0]+=1;self.io.t=33.
                rows=original(label,deadline)
                for row in rows:row['remaining_seconds']=40
                return rows
            rows=original(label,deadline)
            if calls[0]:
                for row in rows:row['remaining_seconds']=None
            return rows
        self.io.frames=later
        result=self.run_goal()
        self.assertLessEqual(result['effective_deadline'],65.)
        self.assertEqual(result['stop_reason'],'observation_failed')
    def test_unknown_countdown_after_grace_does_not_block_color_feedback(self):
        original=self.io.frames;shifted=[False]
        def frames(label,deadline):
            if label.endswith('_after') and not shifted[0]:
                self.io.t+=32.;shifted[0]=True
            rows=original(label,deadline)
            for row in rows:row['remaining_seconds']=None
            return rows
        self.io.frames=frames;result=self.run_goal()
        self.assertTrue(result['accepted']);self.assertEqual(result['effective_deadline'],90.)
        self.assertGreater(result['elapsed_seconds'],30.)
    def test_startup_grace_does_not_hide_session_failures(self):
        self.io.input_backend=lambda deadline:(_ for _ in ()).throw(ValueError('session changed'))
        result=self.run_goal()
        self.assertEqual(result['stop_reason'],'observation_failed')
        self.assertEqual(result['initial_visual_retries'],0);self.assertEqual(self.io.actions,[])
    def test_startup_timeout_never_extends_engineering_limit(self):
        self.io.frames=lambda label,deadline:(_ for _ in ()).throw(TimeoutError('OCR'))
        result=self.run_goal(engineering_deadline=35.,pause=lambda seconds:setattr(self.io,'t',self.io.t+seconds))
        self.assertEqual(self.io.actions,[]);self.assertLessEqual(result['effective_deadline'],35.)
    def test_user_mixed_goal_runs_two_independently_referenced_rounds(self):
        result=self.run_goal()
        self.assertEqual(result['stop_reason'],'target_observed');self.assertTrue(result['accepted'])
        self.assertEqual(len(self.io.actions),2);self.assertEqual(len(result['planning_rounds']),1)
        self.assertEqual(result['actual_colors'],[r['colors'][0] for r in self.io.case['rules']])
        self.assertFalse(result['server_confirmation_verified']);self.assertEqual(self.io.releases,1)
    def test_verified_exact_suffix_finishes_without_switching_global_target(self):
        from native_live.same_session_dye_planner import plan_from_checkpoint
        calls=[]
        def planner(*args,**kwargs):
            calls.append(True)
            return plan_from_checkpoint(*args,**kwargs)
        result=self.run_goal(planner=planner)
        self.assertTrue(result['accepted']);self.assertEqual(len(calls),1)
        self.assertEqual(len(result['planning_rounds']),1)
        self.assertEqual(len(result['planning_rounds'][0]['candidate']['input_route']),2)

    def test_route_intermediates_use_native_readback_and_endpoint_still_uses_screenshots(self):
        from native_live.same_session_dye_planner import plan_from_checkpoint
        labels=[];original=self.io.frames
        def frames(label,deadline):
            labels.append(label)
            return original(label,deadline)
        self.io.frames=frames
        result=self.run_goal()
        self.assertTrue(result['accepted'])
        self.assertEqual(len(self.io.actions),2)
        self.assertNotIn('candidate_0_after',labels)
        self.assertIn('candidate_0_step_1_after',labels)
        self.assertFalse(result['steps'][0]['screenshot_verified'])
        self.assertTrue(result['steps'][1]['screenshot_verified'])

    def test_intermediate_native_acceptance_needs_independent_screenshot_confirmation(self):
        original=self.io.frames
        def frames(label,deadline):
            if label.startswith('candidate_'):raise ValueError('Final screenshot unavailable')
            return original(label,deadline)
        self.io.frames=frames
        result=self.run_goal()
        self.assertFalse(result['accepted'])
        self.assertFalse(result['verified'])

    def test_native_filled_ocr_omissions_cannot_certify_a_precise_target(self):
        from native_live.project_probe_io import merge_native_hex
        original=self.io.frames
        def frames(label,deadline):
            rows=original(label,deadline)
            if label.startswith('candidate_'):
                return [merge_native_hex(dict(row,hex=[None]*3),row['hex']) for row in rows]
            return rows
        self.io.frames=frames
        result=self.run_goal()
        self.assertFalse(result['accepted'])
        self.assertFalse(result['steps'][-1]['screenshot_verified'])
    def test_already_matched_user_rules_never_perturb_the_board(self):
        rules=[dict(enabled=True,exact=True,colors=[c],tolerance=0) for c in self.io.cp['client_hex']]
        result=self.run_goal(rules);self.assertEqual(self.io.actions,[]);self.assertTrue(result['accepted'])
        self.assertEqual(result['planning_rounds'],[])
    def test_user_tolerance_and_disabled_regions_are_preserved(self):
        color=self.io.cp['client_hex'][0];near='#%02X%s'%(int(color[1:3],16)+1,color[3:])
        rules=[dict(enabled=True,exact=False,colors=[near],tolerance=5.),
            dict(enabled=False,exact=True,colors=[],tolerance=0),dict(enabled=False,exact=True,colors=[],tolerance=0)]
        result=self.run_goal(rules);self.assertTrue(result['accepted']);self.assertFalse(result['target_exact'])
        self.assertEqual(self.io.actions,[]);self.assertEqual(result['rules'][0]['colors'],[near])
    def test_no_candidate_stops_with_verified_current_colors_without_diagnostic_input(self):
        result=self.run_goal(planner=lambda *a,**kw:dict(candidate=None,stop_reason='not_found_in_budget'))
        self.assertEqual(result['stop_reason'],'not_found_in_budget');self.assertEqual(self.io.actions,[])
        self.assertTrue(result['verified']);self.assertFalse(result['accepted'])
    def test_bad_visual_and_low_time_send_no_input(self):
        self.io.bad_frames=True;result=self.run_goal();self.assertEqual(self.io.actions,[])
        self.assertFalse(result['verified'])
        self.io=FixtureIO();result=self.run_goal(engineering_deadline=5.)
        self.assertEqual(self.io.actions,[])
        self.assertEqual(result['stop_reason'],'insufficient_time')
    def test_repeated_small_response_error_keeps_bounded_actual_feedback(self):
        self.io.wrong_pose=True;result=self.run_goal(max_rounds=2,max_actions=2)
        self.assertNotEqual(result['stop_reason'],'model_response_mismatch')
        self.assertLessEqual(len(self.io.actions),2)
        self.assertTrue(result['steps'][0].get('model_response_warning'))

    def test_model_response_mismatch_replans_from_actual_readback(self):
        self.io.wrong_pose=True
        original=self.io.perform_candidate;calls=[0]
        def perform(record,label,deadline):
            self.io.wrong_pose=calls[0]==0;calls[0]+=1
            return original(record,label,deadline)
        self.io.perform_candidate=perform
        result=self.run_goal(max_rounds=2)
        self.assertNotEqual(result['stop_reason'],'model_response_mismatch')
        self.assertTrue(result['verified'])

    def test_cursor_trace_mismatch_is_a_warning_when_readback_is_valid(self):
        original=self.io.perform_candidate
        def perform(record,label,deadline):
            receipt=original(record,label,deadline)
            receipt['actual_trace']=[]
            return receipt
        self.io.perform_candidate=perform
        result=self.run_goal()
        self.assertTrue(result['verified'])
        self.assertNotEqual(result['stop_reason'],'cursor_trace_mismatch')
    def test_failed_revalidation_never_displays_an_old_checkpoint_as_current(self):
        original=self.io.frames
        def frames(label,deadline):
            if label.endswith('_revalidate'):raise ValueError('Current HEX unavailable')
            return original(label,deadline)
        self.io.frames=frames;result=self.run_goal()
        self.assertEqual(self.io.actions,[]);self.assertFalse(result['verified'])
        self.assertEqual(result['actual_colors'],[None]*3)
    def test_cancellation_and_action_limit_are_not_bypassed(self):
        self.io.cancel=True;result=self.run_goal();self.assertEqual(self.io.actions,[])
        self.assertEqual(result['stop_reason'],'interrupted')
        self.io=FixtureIO();result=self.run_goal(max_actions=1,max_rounds=1)
        self.assertEqual(len(self.io.actions),0);self.assertFalse(result['accepted'])
        self.assertEqual(result['stop_reason'],'insufficient_route_actions')
        self.assertTrue(result['verified'])
        self.assertEqual(result['actual_colors'],self.io.cp['client_hex'])


if __name__=='__main__':unittest.main()
