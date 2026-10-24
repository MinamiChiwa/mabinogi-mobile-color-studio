"""Recorded rc6 endpoint regression; file IO and modeled inputs only."""
import copy
import hashlib
import json
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from native_input_response import InputGeometry, InputSettings, replay_native_route
from native_palette_scoring import load_session, score_native_pose
from native_live.same_session_dye_planner import _json, _plan_fingerprint, audit_candidate_endpoint,bind_planning_context

FIXTURE = Path(__file__).resolve().parents[2] / 'fixtures/native-route-feedback'


class RecordedRouteIO:
    """Inject the real first rotation residual, then use conditional replay.

    No process handles, Windows API or game input are available in this fake.
    The controller, palette evaluator and corrective route generation are real.
    """
    def __init__(self, *, cancel_after_first=False, error_on_final=False):
        self.case = json.loads((FIXTURE/'route-case.json').read_text(encoding='utf-8'))
        self.session = load_session(FIXTURE)
        # The archived colors/pose remain evidence; ranking is derived policy
        # metadata and must be regenerated after changing that policy.
        candidate = self.case['candidate']
        candidate['prediction']['rank'] = score_native_pose(self.session,
            candidate['final_pose'],self.case['rules'])['rank']
        self.cp = copy.deepcopy(self.case['checkpoint'])
        self.settings = InputSettings(**self.case['settings'])
        self.geometry = InputGeometry(self.cp['board'], self.cp['local_size'], 'windows_legacy_mouse_pixels')
        self.pose = copy.deepcopy(self.cp['pose'])
        self.started = time.monotonic()
        self.actions = []
        self.cancel_after_first = cancel_after_first
        self.error_on_final = error_on_final

    def clock(self):return 1. + time.monotonic()-self.started
    def check(self, deadline):
        if self.cancel_after_first and self.actions:raise InterruptedError('F9')
        if self.clock() >= deadline:raise TimeoutError('deadline')
    planning_check = check
    def input_backend(self, deadline):
        self.check(deadline)
        return dict(process_identity=json.loads(self.cp['binding'])[1],backend_object='file-only',
            backend_type='MM.Client.Framework.InputSystem.InputManager',input_assistant='0x0',
            legacy_mouse_getter_rva='0x185310',viewport_origin=[0,0],viewport_scale=[1.,1.])
    def checkpoint(self, label, deadline):
        self.check(deadline)
        cp = dict(copy.deepcopy(self.cp), label=label, pose=copy.deepcopy(self.pose))
        cp['client_hex'] = score_native_pose(self.session, self.pose, self.case['rules'])['colors']
        return cp
    def frames(self, label, deadline):
        cp = self.checkpoint(label, deadline)
        now = self.clock()
        return [dict(hex=cp['client_hex'],remaining_seconds=None,captured_monotonic=now+offset,
            screenshot_hex=cp['client_hex'],hex_source=['screenshot']*3,screenshot_hex_verified=True)
            for offset in (-.001,0.)]
    def perform_candidate(self, record, label, deadline):
        self.check(deadline)
        self.actions.append(copy.deepcopy(record))
        if len(self.actions)==1 and not self.error_on_final:self.pose=copy.deepcopy(self.case['measured_first_response'])
        else:self.pose=replay_native_route(self.pose,[record],self.geometry,self.settings,
            wheel_delta_per_step=1.,sample_policy='all_recorded_points')['final_pose']
        if self.error_on_final and len(self.actions)==len(self.case['candidate']['input_route']):
            self.pose['rotation_degrees']+=3.847992
        return dict(completed=True,released=True,input_source='recorded_plus_simulated_response',gesture=record,
            actual_trace=[dict(actual_client=list(point)) for point in record['points']])
    def release(self):pass
    def plan(self, context, cp, frames, rules, grid, **kw):
        row = audit_candidate_endpoint(context,cp,rules,self.case['candidate'])
        plan = dict(schema=4,context_fingerprint=context['fingerprint'],reference_pose=cp['pose'],
            reference_frame_monotonic=frames[-1]['captured_monotonic'],planned_at=self.clock(),
            effective_deadline=kw['engineering_deadline'],reserve_seconds=3.,verification_margin_seconds=3.,
            normalized_rules=rules,rules_fingerprint=hashlib.sha256(_json(rules).encode()).hexdigest(),
            candidate=None,compromise_candidate=row,approach_candidate=None,
            nearest_diagnostic=row,reachability_conclusion='not_established',
            result_classification='not_found_in_budget',stop_reason='no_supported_accepted_candidate')
        plan['plan_fingerprint']=_plan_fingerprint(plan)
        return plan


class NativeRouteFeedbackTests(unittest.TestCase):
    def run_case(self, **kw):
        from native_live.controller import run_goal_loop
        io=RecordedRouteIO(**kw)
        # Local refinement is a separate contract; this regression isolates
        # whether the global route reaches its original endpoint after error.
        with patch('native_live.controller.find_refinement',return_value=None):
            result=run_goal_loop(io,io.session,io.settings,io.case['rules'],
                engineering_deadline=100.,clock=io.clock,planner=io.plan)
        return io,result

    def test_recorded_rotation_error_preserves_joint_white_destination(self):
        io,result=self.run_case()
        self.assertEqual(result['stop_reason'],'compromise_observed',result.get('error'))
        self.assertEqual(result['actual_colors'][:2],['#FFFFFF','#FFFFFF'])
        self.assertLessEqual(result['actual_deltas'][2],10.)
        self.assertTrue(result['screenshot_verified'])
        self.assertGreater(len(io.actions),1)

    def test_user_stop_after_rotation_never_runs_correction_input(self):
        io,result=self.run_case(cancel_after_first=True)
        self.assertEqual(result['stop_reason'],'interrupted')
        self.assertEqual(len(io.actions),1)
        self.assertFalse(result['verified'])

    def test_final_gesture_residual_is_corrected_before_local_refinement(self):
        io,result=self.run_case(error_on_final=True)
        self.assertEqual(result['stop_reason'],'compromise_observed',result.get('error'))
        self.assertEqual(result['actual_colors'][:2],['#FFFFFF','#FFFFFF'])
        self.assertLessEqual(result['actual_deltas'][2],10.)
        self.assertTrue(result['screenshot_verified'])

    def correct_final(self, rules):
        from native_live.route_feedback import correct_remaining_route
        io=RecordedRouteIO()
        context=bind_planning_context(io.session,io.cp,io.geometry,io.settings,
            wheel_delta_per_step=1.,calibration_evidence=dict(source='recorded',viewport_origin=[0,0],
                viewport_scale=[1,1],backend_during_actions_synchronously_recorded=True))
        io.pose=copy.deepcopy(io.case['candidate']['final_pose'])
        io.pose['rotation_degrees']+=3.847992
        cp=io.checkpoint('measured_final',100.)
        return correct_remaining_route(context,cp,rules,[],expected_pose=io.case['candidate']['final_pose'],
            target_pose=io.case['candidate']['final_pose'],deadline=io.clock()+3.,clock=io.clock)

    def test_destination_restoration_keeps_disabled_region_disabled(self):
        rules=RecordedRouteIO().case['rules']
        rules[2].update(enabled=False,colors=[])
        original=copy.deepcopy(rules)
        row=self.correct_final(rules)
        self.assertIsNotNone(row)
        self.assertEqual(row['prediction']['colors'],['#FFFFFF','#FFFFFF',None])
        self.assertIsNone(row['prediction']['deltas'][2])
        self.assertTrue(row['prediction']['predicted_accepted'])
        self.assertEqual(rules,original)

    def test_destination_restoration_reports_user_similar_tolerance(self):
        rules=RecordedRouteIO().case['rules']
        rules[2].update(exact=False,tolerance=10.)
        original=copy.deepcopy(rules)
        row=self.correct_final(rules)
        self.assertIsNotNone(row)
        self.assertEqual(row['prediction']['colors'],['#FFFFFF','#FFFFFF','#E1E6E2'])
        self.assertTrue(row['prediction']['predicted_accepted'])
        self.assertFalse(row['prediction']['target_exact'])
        self.assertAlmostEqual(row['prediction']['deltas'][2],9.70765,places=4)
        self.assertEqual(rules,original)

    def test_correction_local_cutoff_includes_replay_and_endpoint_audit(self):
        from native_live.route_feedback import correct_remaining_route
        io=RecordedRouteIO();context=bind_planning_context(io.session,io.cp,io.geometry,io.settings,
            wheel_delta_per_step=1.,calibration_evidence=dict(source='recorded',viewport_origin=[0,0],
                viewport_scale=[1,1],backend_during_actions_synchronously_recorded=True))
        io.pose=io.case['measured_first_response'];cp=io.checkpoint('measured',100.)
        ticks=[0.]
        def check():ticks[0]+=.001
        row=correct_remaining_route(context,cp,io.case['rules'],io.case['candidate']['input_route'][1:],
            expected_pose=io.case['candidate']['final_pose'],target_pose=io.case['candidate']['final_pose'],
            deadline=.02,clock=lambda:ticks[0],check=check)
        self.assertIsNone(row)
        self.assertLessEqual(ticks[0],.025,'CPU replay/audit must not bypass the local correction cutoff')


if __name__=='__main__':unittest.main()
