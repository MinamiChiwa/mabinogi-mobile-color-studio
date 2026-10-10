"""Recovery must execute a whole audited route, including opposite wheels."""
import copy
import hashlib
import unittest
from unittest.mock import patch

from input_gestures import wheel_gesture
from native_input_compile import native_drag_gesture
from native_input_response import replay_native_route
from native_input_route_search import _needed
from native_palette_scoring import score_native_pose
from native_live.controller import run_goal_loop
from native_live.same_session_dye_planner import audit_candidate_endpoint,_plan_fingerprint,_json
import test_native_live_compromise as compromise_fixture


class BestRestoreRouteTests(unittest.TestCase):
    def setUp(self):
        fixture=compromise_fixture.NativeCompromiseTests();fixture.setUp()
        self.io=fixture.io;self.rules=fixture.rules;self.io.clock=lambda:self.io.t
        self.bad_pose=copy.deepcopy(self.io.pose)
        self.recovery_route=[wheel_gesture(self.io.geometry.board,1).record(),
            wheel_gesture(self.io.geometry.board,-1).record(),
            native_drag_gesture(self.io.geometry,self.io.settings,5,0).record()]
        self.io.pose=self.replay(self.bad_pose,self.recovery_route)
        self.baseline_colors=score_native_pose(self.io.session,self.io.pose,self.rules)['colors']
        self.io.cp=dict(self.io.cp,pose=copy.deepcopy(self.io.pose),client_hex=self.baseline_colors)
        perform=self.io.perform_candidate
        def drifted_compromise(record,label,deadline):
            result=perform(record,label,deadline)
            if len(self.io.actions)==1:self.io.pose=copy.deepcopy(self.bad_pose)
            if getattr(self,'perturb_restore',False) and label=='restore_0':
                self.io.pose['position'][0]+=.0000003
            if getattr(self,'cancel_restore',False) and label.startswith('restore_'):
                self.io.cancel=True
            return result
        self.io.perform_candidate=drifted_compromise
        self.restoration_calls=0

    def replay(self,pose,route):
        return replay_native_route(pose,route,self.io.geometry,self.io.settings,
            wheel_delta_per_step=1.,sample_policy='all_recorded_points')['final_pose']

    def plan(self,context,cp,frames,rules,grid,*,restore=False,**kwargs):
        if restore:self.restoration_calls+=1
        route=self.recovery_route if restore else [native_drag_gesture(self.io.geometry,self.io.settings,-5,0).record()]
        final=self.replay(cp['pose'],route)
        row=audit_candidate_endpoint(context,cp,rules,dict(input_route=copy.deepcopy(route),final_pose=final,
            prediction=score_native_pose(self.io.session,final,rules),needed=_needed(route,3.,.5),
            source='saved_three_leg_recovery_contract'))
        plan=dict(schema=4,context_fingerprint=context['fingerprint'],reference_pose=cp['pose'],
            reference_frame_monotonic=frames[-1]['captured_monotonic'],planned_at=self.io.clock(),
            effective_deadline=kwargs['engineering_deadline'],candidate=row if restore else None,
            approach_candidate=None,compromise_candidate=None if restore else row,
            reserve_seconds=10.,verification_margin_seconds=8.,normalized_rules=rules,
            rules_fingerprint=hashlib.sha256(_json(rules).encode()).hexdigest(),
            result_classification='predicted_exact' if restore else 'not_found_in_budget',
            nearest_diagnostic=None,reachability_conclusion='not_established')
        plan['plan_fingerprint']=_plan_fingerprint(plan)
        return plan

    def run_loop(self,**kwargs):
        with patch('native_live.controller.plan_from_checkpoint',side_effect=lambda *a,**k:self.plan(*a,restore=True,**k)), \
             patch('native_live.controller.find_refinement',return_value=None):
            return run_goal_loop(self.io,self.io.session,self.io.settings,self.rules,
                engineering_deadline=90.,clock=self.io.clock,planner=self.plan,**kwargs)

    def test_three_leg_opposite_wheel_route_restores_actual_best_without_research(self):
        result=self.run_loop()
        restores=[step for step in result['steps'] if step['purpose']=='restore_best']
        self.assertEqual(len(restores),3)
        self.assertEqual(self.restoration_calls,1)
        self.assertEqual(result['actual_colors'],self.baseline_colors)
        self.assertTrue(result['restored']);self.assertTrue(result['best_current'])
        self.assertFalse(restores[0]['screenshot_verified'])
        self.assertFalse(restores[1]['screenshot_verified'])
        self.assertTrue(restores[2]['screenshot_verified'])
        self.assertFalse(result['accepted'])

    def test_stop_during_first_restore_leg_never_sends_the_remaining_pair(self):
        self.cancel_restore=True;result=self.run_loop()
        self.assertEqual(len(self.io.actions),2)
        self.assertEqual(result['stop_reason'],'interrupted')
        self.assertFalse(result.get('restored',False))

    def test_small_restore_residual_continues_the_audited_suffix(self):
        self.perturb_restore=True;result=self.run_loop()
        steps=[step for step in result['steps'] if step['purpose']=='restore_best']
        self.assertEqual(len(steps),3)
        self.assertTrue(steps[0]['remaining_route_audit']['continued'])
        self.assertEqual(steps[1]['before']['pose'],steps[0]['after']['pose'])
        self.assertEqual(result['actual_colors'],self.baseline_colors)
        self.assertTrue(result['restored'])

    def test_native_filled_endpoint_does_not_claim_verified_best_restoration(self):
        from native_live.project_probe_io import merge_native_hex
        frames=self.io.frames
        def missing_screenshot(label,deadline):
            rows=frames(label,deadline)
            if label.startswith('restore_'):
                return [merge_native_hex(dict(row,hex=[None]*3),row['hex']) for row in rows]
            return rows
        self.io.frames=missing_screenshot;result=self.run_loop()
        self.assertEqual(result['actual_colors'],self.baseline_colors)
        self.assertFalse(result['screenshot_verified'])
        self.assertFalse(result['restored'])

    def test_insufficient_whole_recovery_quota_keeps_current_without_partial_restore(self):
        result=self.run_loop(max_actions=3)
        self.assertEqual(len(self.io.actions),1)
        self.assertFalse(result['restored'])
        self.assertNotEqual(result['actual_colors'],self.baseline_colors)


if __name__=='__main__':unittest.main()
