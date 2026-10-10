"""Recovery uses new observations, never repeats an uncertain input."""
import copy,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from test_native_live_controller import FixtureIO
from native_live.controller import run_goal_loop
from native_live.dye_visual_readiness import VisualNotReady


class RecoveryTests(unittest.TestCase):
    def test_focus_flag_is_not_a_session_identity(self):
        from native_live.dye_action_checkpoint import _binding
        io=FixtureIO()
        raw=json.loads(io.cp['binding'])
        context=raw[4]
        first=dict(session_token=raw[0],process_identity=raw[1],
                   motion={'binding':raw[2],'settings':raw[3]},window_context=context)
        second=copy.deepcopy(first)
        second['window_context']['window']['foreground']=not second['window_context']['window'].get('foreground',True)
        self.assertEqual(_binding(first),_binding(second))
        second['window_context']['window']['hwnd']=123456
        self.assertNotEqual(_binding(first),_binding(second))

    def test_focus_return_before_input_does_not_force_a_restart(self):
        from native_live import project_probe_io as module
        io=object.__new__(module.ProjectProbeIO)
        import threading
        io.stop=threading.Event();io.f9_pressed=lambda:False;io.deadline=100.
        attempts=[];tick=[1.]
        def game_check():
            attempts.append(1)
            if len(attempts)==1:
                raise RuntimeError('已暂停：游戏失去焦点。返回游戏后按 F8 重新开始。')
        io.original_game_check=game_check;io._performing_input=False
        with patch.object(module.time,'monotonic',side_effect=lambda:tick[0]), \
             patch.object(module.time,'sleep',side_effect=lambda seconds:tick.__setitem__(0,tick[0]+seconds)):
            io._input_guard()
        self.assertEqual(len(attempts),2)

    def test_focus_loss_inside_gesture_stops_immediately(self):
        from native_live import project_probe_io as module
        import threading
        io=object.__new__(module.ProjectProbeIO)
        io.stop=threading.Event();io.f9_pressed=lambda:False;io.deadline=100.;io._performing_input=True
        io.original_game_check=lambda:(_ for _ in ()).throw(RuntimeError('已暂停：游戏失去焦点。返回游戏后按 F8 重新开始。'))
        with patch.object(module.time,'monotonic',return_value=1.),patch.object(module.time,'sleep') as pause:
            with self.assertRaises(InterruptedError):io._input_guard()
        pause.assert_not_called()

    def run_fixture(self, io, **kwargs):
        return run_goal_loop(io,io.session,io.settings,io.case['rules'],
            engineering_deadline=90.,clock=io.clock,
            pause=lambda seconds:setattr(io,'t',io.t+seconds),**kwargs)

    def test_temporary_visual_failure_after_input_recovers_without_repeating_action(self):
        io=FixtureIO();original=io.frames;failed=[]
        def frames(label,deadline):
            if label.startswith('candidate_') and label.endswith('_after') and not failed:
                failed.append(label);raise VisualNotReady('cards updating')
            return original(label,deadline)
        io.frames=frames;result=self.run_fixture(io)
        self.assertTrue(result['accepted'],result.get('error'))
        self.assertEqual(len(io.actions),2)
        self.assertEqual(result['observation_retries'],1)

    def test_temporary_visual_failure_before_input_recovers(self):
        io=FixtureIO();original=io.frames;failed=[]
        def frames(label,deadline):
            if label=='plan_0_revalidate' and not failed:
                failed.append(label);raise VisualNotReady('cards updating')
            return original(label,deadline)
        io.frames=frames;result=self.run_fixture(io)
        self.assertTrue(result['accepted'],result.get('error'))
        self.assertEqual(len(io.actions),2)

    def test_changed_preinput_pose_replans_instead_of_submitting_old_route(self):
        io=FixtureIO();original=io.checkpoint;changed=[]
        def checkpoint(label,deadline):
            if label=='plan_0_revalidate' and not changed:
                io.pose['position'][0]+=.001;changed.append(True)
            return original(label,deadline)
        io.checkpoint=checkpoint;result=self.run_fixture(io,max_rounds=2)
        self.assertEqual(result['reference_replans'],1)
        self.assertNotEqual(result['stop_reason'],'observation_failed')
        for step in result['steps']:
            self.assertNotEqual(step['before']['pose'],io.cp['pose'])

    def test_merge_retains_raw_screenshot_values_and_does_not_claim_ocr_verification(self):
        from native_live.project_probe_io import merge_native_hex
        frame={'hex':['#112233',None,'#AABBCC']}
        merged=merge_native_hex(frame,['#112233','#445566','#AABBCC'])
        self.assertEqual(merged['screenshot_hex'],frame['hex'])
        self.assertFalse(merged['screenshot_hex_verified'])
        self.assertIsNone(frame['hex'][1])

    def test_large_model_error_rebases_instead_of_stopping_an_authorized_route(self):
        io=FixtureIO();original=io.perform_candidate
        def perform(*args):
            receipt=original(*args);io.pose['position'][0]+=.2;return receipt
        io.perform_candidate=perform;result=self.run_fixture(io,max_rounds=1)
        self.assertNotEqual(result['stop_reason'],'model_response_mismatch')
        self.assertGreaterEqual(len(io.actions),2)
        self.assertTrue(result['verified'])
        audit=result['steps'][0]['remaining_route_audit']
        self.assertTrue(audit['continued'])
        self.assertEqual(audit['reference_pose'],result['steps'][0]['after']['pose'])

    def test_unknown_input_completion_never_retries_input(self):
        io=FixtureIO();original=io.perform_candidate
        def perform(*args):
            receipt=original(*args);receipt['completed']=False;return receipt
        io.perform_candidate=perform;result=self.run_fixture(io)
        self.assertEqual(result['stop_reason'],'input_outcome_unknown')
        self.assertEqual(len(io.actions),1);self.assertFalse(result['verified'])

    def test_unexpected_execution_error_is_saved_with_traceback(self):
        io=FixtureIO()
        io.perform_candidate=lambda *args:(_ for _ in ()).throw(TypeError('integration failure'))
        result=self.run_fixture(io)
        self.assertEqual(result['stop_reason'],'internal_error')
        self.assertIn('TypeError',result['error_traceback'])
        self.assertFalse(result['verified']);self.assertEqual(io.actions,[])

    def test_model_warning_rebases_all_remaining_inputs_from_actual_readback(self):
        import test_native_live_compromise as fixture
        setup=fixture.NativeCompromiseTests();setup.setUp();io=setup.io
        original=io.perform_candidate
        def perform(*args):
            receipt=original(*args)
            if len(io.actions)==1:io.pose['position'][0]+=.001
            return receipt
        io.perform_candidate=perform
        result=run_goal_loop(io,io.session,io.settings,setup.rules,engineering_deadline=90.,
            clock=io.clock,max_rounds=2)
        self.assertTrue(result['steps'][0].get('model_response_warning'))
        import numpy as np
        audit=result['steps'][0]['remaining_route_audit']
        self.assertTrue(audit['continued'])
        self.assertEqual(audit['reference_pose'],result['steps'][0]['after']['pose'])
        self.assertEqual(result['steps'][1]['before']['pose'],result['steps'][0]['after']['pose'])


class ServiceIntegrationTests(unittest.TestCase):
    def run_service(self,io,rules,planner=None):
        from engine import Runner
        from native_live import service
        from window_target import WindowTarget
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);events=[]
            owner=Runner(lambda kind,data:events.append((kind,data)),folder)
            # This fixture models IO in its own clock. Waiting for an absent
            # test UI must advance that clock, not spend a real 80-second round.
            def poll_choice(batch_id,deadline):
                io.t=max(io.t,deadline)
                return None
            owner.wait_candidate_choice=poll_choice
            baseline=dict(stop_reason='passive_baseline_collected',session_deadline_monotonic=90.,
                capture={'capture_folder':'fixture'},baseline={'motion':{'settings':io.case['settings']}})
            backend=SimpleNamespace(close=lambda:None)
            def loop(adapter,session,settings,received,**kwargs):
                if planner is not None:kwargs['planner']=planner
                return run_goal_loop(adapter,session,settings,received,clock=io.clock,
                    pause=lambda seconds:setattr(io,'t',io.t+seconds),**kwargs)
            with patch.object(service,'_prepare',return_value=(backend,{})), \
                 patch.object(service,'resolve_target',return_value=WindowTarget(20,123,'Game','MabinogiMobile.exe')), \
                 patch.object(service,'collect_validation_session',return_value=baseline), \
                 patch.object(service,'load_session',return_value=io.session), \
                 patch.object(service,'ProjectClosedLoopIO',return_value=io), \
                 patch.object(service,'run_goal_loop',side_effect=loop), \
                 patch.object(service.u,'GetAsyncKeyState',return_value=0):
                io.input_attempts=0
                original=io.perform_candidate
                def perform(*args,**kwargs):
                    io.input_attempts+=1
                    return original(*args,**kwargs)
                io.perform_candidate=perform
                result=service.run_native_search(owner,rules)
            saved=json.loads((folder/'native-result.json').read_text(encoding='utf-8'))
            self.assertEqual(saved['stop_reason'],result['stop_reason'])
            actions=[d for k,d in events if k=='native_progress' and 'action_kind' in d]
            self.assertEqual(len(actions),len(io.actions))
            self.assertTrue(actions)
            owner.store.close()
            return result

    def test_exact_route_reaches_real_runner_event_and_saved_result(self):
        io=FixtureIO();result=self.run_service(io,io.case['rules'])
        self.assertTrue(result['accepted']);self.assertEqual(len(io.actions),2)

    def test_two_enabled_regions_compromise_reaches_real_runner_event(self):
        from test_native_live_compromise import NativeCompromiseTests
        setup=NativeCompromiseTests();setup.setUp();io=setup.io
        rules=[dict(enabled=i<2,exact=True,colors=['#000000'] if i<2 else [],tolerance=0.) for i in range(3)]
        def forced_compromise(context,cp,frames,received,grid,**kwargs):
            import hashlib
            from native_live.same_session_dye_planner import plan_from_checkpoint,_plan_fingerprint,_json
            from native_input_compile import native_drag_gesture
            from native_input_response import replay_native_route
            from native_input_route_search import _needed
            from native_palette_scoring import score_native_pose
            neutral=[dict(enabled=True,exact=True,colors=[c],tolerance=0.) for c in cp['client_hex']]
            plan=plan_from_checkpoint(context,cp,frames,neutral,grid,**kwargs)
            route=[native_drag_gesture(io.geometry,io.settings,5,0).record()]
            pose=replay_native_route(cp['pose'],route,io.geometry,io.settings,
                wheel_delta_per_step=1.,sample_policy='all_recorded_points')['final_pose']
            row=dict(input_route=route,final_pose=pose,prediction=score_native_pose(io.session,pose,received),
                needed=_needed(route,3.,.5),source='explicit_unmatched_test_route')
            plan.update(candidate=None,compromise_candidate=row,approach_candidate=None,
                normalized_rules=received,rules_fingerprint=hashlib.sha256(_json(received).encode()).hexdigest(),
                result_classification='not_found_in_budget')
            plan['plan_fingerprint']=_plan_fingerprint(plan)
            return plan
        result=self.run_service(io,rules,planner=forced_compromise)
        self.assertEqual(result['outcome'],'compromise');self.assertFalse(result['accepted'])
        self.assertIsNone(result['actual_deltas'][2])
