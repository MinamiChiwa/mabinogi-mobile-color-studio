"""A speculative improvement must fit its measured return and verification."""
import copy,hashlib,unittest
from unittest.mock import patch
import test_native_live_compromise as compromise_fixture
from native_input_compile import native_drag_gesture
from native_input_response import replay_native_route
from native_input_route_search import _needed
from native_palette_scoring import score_native_pose
from native_live.compromise import observed_quality
from native_live.same_session_dye_planner import audit_candidate_endpoint,_plan_fingerprint,_json
from native_live.controller import run_goal_loop


class ProtectedRefinementControllerTests(unittest.TestCase):
    def setUp(self):
        fixture=compromise_fixture.NativeCompromiseTests();fixture.setUp()
        self.io=fixture.io;self.rules=fixture.rules;self.io.clock=lambda:self.io.t
        self.baseline=copy.deepcopy(self.io.pose)
        checkpoint=self.io.checkpoint;frames=self.io.frames;perform=self.io.perform_candidate
        # Include native/visual overhead at the measured live scale.
        def read(label,deadline):
            self.io.t+=.7;return checkpoint(label,deadline)
        def visual(label,deadline):
            self.io.t+=2.;return frames(label,deadline)
        def action(record,label,deadline):
            self.io.t+=record['input_seconds']+.2;return perform(record,label,deadline)
        self.io.checkpoint=read;self.io.frames=visual;self.io.perform_candidate=action
        self.refiner_calls=0

    def candidate(self,context,cp,route,rules=None):
        rules=self.rules if rules is None else rules
        pose=replay_native_route(cp['pose'],route,self.io.geometry,self.io.settings,
            wheel_delta_per_step=1.,sample_policy='all_recorded_points')['final_pose']
        return audit_candidate_endpoint(context,cp,rules,dict(input_route=route,final_pose=pose,
            prediction=score_native_pose(self.io.session,pose,rules),needed=_needed(route,3.,.5),source='test_real_route'))

    def plan(self,context,cp,frames,rules,grid,**kw):
        row=self.candidate(context,cp,[])
        plan=dict(schema=4,context_fingerprint=context['fingerprint'],reference_pose=cp['pose'],
            reference_frame_monotonic=frames[-1]['captured_monotonic'],planned_at=self.io.t,
            effective_deadline=kw['engineering_deadline'],candidate=None,approach_candidate=None,
            compromise_candidate=row,reserve_seconds=10.,verification_margin_seconds=8.,
            normalized_rules=rules,rules_fingerprint=hashlib.sha256(_json(rules).encode()).hexdigest(),
            result_classification='not_found_in_budget',nearest_diagnostic=None,
            reachability_conclusion='not_established',seed_mode='test_verified_baseline',
            stop_reason='no_supported_accepted_candidate')
        plan['plan_fingerprint']=_plan_fingerprint(plan);return plan

    def refine(self,context,cp,rules,**kw):
        self.refiner_calls+=1
        if self.refiner_calls>1:return None
        drag=native_drag_gesture(self.io.geometry,self.io.settings,5,0).record()
        row=self.candidate(context,cp,[drag])
        endpoint=copy.deepcopy(cp);endpoint.update(pose=row['final_pose'],client_hex=row['prediction']['colors'])
        back=native_drag_gesture(self.io.geometry,self.io.settings,-5,0).record()
        recovery=self.candidate(context,endpoint,[back])
        row.update(recovery_route=[back],recovery_candidate=recovery,prefix_recoveries=[recovery])
        return row

    def recover(self,context,cp,baseline,rules,**kw):
        width=self.io.geometry.board[2]-self.io.geometry.board[0]
        height=self.io.geometry.board[3]-self.io.geometry.board[1]
        dx=round((baseline['pose']['position'][0]-cp['pose']['position'][0])*width)
        dy=round((baseline['pose']['position'][1]-cp['pose']['position'][1])*height)
        gesture=native_drag_gesture(self.io.geometry,self.io.settings,dx,dy)
        return self.candidate(context,cp,[gesture.record()] if gesture.has_effect else [])

    def run_loop(self,deadline=90.,refine=None,recover=None,**kw):
        with patch('native_live.controller.find_refinement',refine or self.refine,create=True), \
             patch('native_live.controller.find_recovery',recover or self.recover,create=True):
            return run_goal_loop(self.io,self.io.session,self.io.settings,self.rules,
                engineering_deadline=deadline,clock=self.io.clock,planner=self.plan,**kw)

    def test_verified_improvement_is_promoted_without_another_global_search(self):
        result=self.run_loop()
        self.assertGreater(len(self.io.actions),0,'Old controller ended before protected refinement')
        self.assertLess(result['maximum'],result['initial_maximum'])
        self.assertTrue(result['best_current']);self.assertTrue(result['screenshot_verified'])
        self.assertEqual(len(result['planning_rounds']),1)
        self.assertEqual(result['refinement_attempts'][0]['status'],'promoted')

    def test_worse_actual_trial_returns_from_actual_pose_before_deadline(self):
        original=self.io.perform_candidate
        def action(record,label,deadline):
            receipt=original(record,label,deadline)
            if len(self.io.actions)==1:
                self.io.pose=replay_native_route(self.baseline,
                    [native_drag_gesture(self.io.geometry,self.io.settings,-5,0).record()],
                    self.io.geometry,self.io.settings,wheel_delta_per_step=1.,sample_policy='all_recorded_points')['final_pose']
            return receipt
        self.io.perform_candidate=action
        result=self.run_loop()
        self.assertGreaterEqual(len(self.io.actions),2)
        self.assertEqual(result['actual_colors'],result['initial']['checkpoint']['client_hex'])
        self.assertEqual(result['refinement_attempts'][0]['status'],'restored')
        self.assertLess(self.io.t,90.-8.)
        self.assertTrue(result['steps'][0].get('model_response_warning'))

    def test_budget_includes_return_and_final_visual_before_any_input(self):
        result=self.run_loop(deadline=23.)
        self.assertEqual(self.io.actions,[])
        self.assertEqual(result.get('refinement_stop'),'insufficient_protected_time')
        self.assertTrue(result['verified']);self.assertTrue(result['best_current'])

    def test_action_quota_is_reserved_for_return_before_trial(self):
        result=self.run_loop(max_actions=1)
        self.assertEqual(self.io.actions,[])
        self.assertEqual(result.get('refinement_stop'),'insufficient_protected_actions')

    def test_expired_local_search_preserves_anchor(self):
        def slow(*a,**kw):
            self.io.t=kw['deadline']+.01;return None
        result=self.run_loop(refine=slow)
        self.assertEqual(self.io.actions,[])
        self.assertTrue(result['verified']);self.assertTrue(result['best_current'])
        self.assertEqual(result['stop_reason'],'compromise_observed')
        self.assertEqual(result.get('refinement_stop'),'no_safe_improvement')

    def test_trial_visual_timeout_uses_reserved_return(self):
        original=self.io.frames
        def frames(label,deadline):
            if label.startswith('refine_') and label.endswith('_after'):
                self.io.t=deadline;raise TimeoutError('probe screenshot deadline')
            return original(label,deadline)
        self.io.frames=frames
        result=self.run_loop()
        self.assertGreaterEqual(len(self.io.actions),2)
        self.assertEqual(result['actual_colors'],result['initial']['checkpoint']['client_hex'])
        self.assertTrue(result['verified']);self.assertLess(self.io.t,82.)

    def test_missing_prefix_recovery_never_admits_trial(self):
        def unsafe(*a,**kw):
            row=self.refine(*a,**kw);row['prefix_recoveries']=[];return row
        result=self.run_loop(refine=unsafe)
        self.assertEqual(self.io.actions,[])
        self.assertEqual(result.get('refinement_stop'),'recovery_not_proven')

    def refine_two(self,context,cp,rules,**kw):
        route=[native_drag_gesture(self.io.geometry,self.io.settings,dx,0).record() for dx in (5,-1)]
        row=self.candidate(context,cp,route);returns=[]
        for index,reverse_dx in enumerate(((-5,),(1,-5))):
            prefix=self.candidate(context,cp,route[:index+1])
            endpoint=dict(cp,pose=prefix['final_pose'],client_hex=prefix['prediction']['colors'])
            back=[native_drag_gesture(self.io.geometry,self.io.settings,dx,0).record() for dx in reverse_dx]
            returns.append(self.candidate(context,endpoint,back))
        row.update(prefix_recoveries=returns,recovery_route=returns[-1]['input_route'])
        return row

    def test_two_returns_reserve_an_extra_correction_action_each(self):
        result=self.run_loop(refine=self.refine_two,max_actions=6)
        self.assertEqual(self.io.actions,[],'Trial plus two corrected three-action returns requires eight slots')
        self.assertEqual(result.get('refinement_stop'),'insufficient_protected_actions')

    def test_local_search_can_use_ten_seconds_without_borrowing_return_time(self):
        offered=[]
        def search(*args,**kw):
            offered.append(kw['deadline']-self.io.clock());return self.refine(*args,**kw)
        result=self.run_loop(deadline=110.,refine=search)
        self.assertGreaterEqual(offered[0],9.9)
        self.assertTrue(result['best_current']);self.assertLess(self.io.t,102.)

    def test_cold_start_visual_cost_does_not_block_warm_refinement(self):
        original=self.io.frames
        def frames(label,deadline):
            if label=='initial':self.io.t+=9.
            return original(label,deadline)
        self.io.frames=frames
        result=self.run_loop(deadline=90.)
        self.assertTrue(self.io.actions,'A one-time cold OCR cost was treated as every future screenshot cost')
        self.assertTrue(result['best_current'])

    def test_known_not_started_trial_keeps_the_anchor(self):
        from native_live.project_closed_loop_io import InputNotStarted
        def expired(*args):raise InputNotStarted('preparation exceeded phase')
        self.io.perform_candidate=expired
        result=self.run_loop()
        self.assertEqual(self.io.actions,[])
        self.assertTrue(result['verified']);self.assertTrue(result['best_current'])
        self.assertEqual(result.get('refinement_stop'),'trial_not_started')

    def test_pre_input_guard_uses_trial_phase_and_preserves_anchor(self):
        from native_live.project_closed_loop_io import validate_research_gesture
        original=self.io.check;armed=[False]
        def validate(*args):
            gesture=validate_research_gesture(*args);armed[0]=True;return gesture
        def check(deadline):
            if armed[0]:
                armed[0]=False
                self.assertLess(deadline,40.,'Pre-input guard borrowed the global rather than trial allowance')
                self.io.t=deadline;raise TimeoutError('focus wait exhausted input phase')
            return original(deadline)
        self.io.check=check
        with patch('native_live.controller.validate_research_gesture',validate):result=self.run_loop()
        self.assertEqual(self.io.actions,[])
        self.assertTrue(result['best_current']);self.assertTrue(result['verified'])
        self.assertEqual(result.get('refinement_stop'),'trial_not_started')

    def test_unknown_refinement_input_never_sends_a_return(self):
        original=self.io.perform_candidate
        def unknown(*args):
            receipt=original(*args);receipt['completed']=False;return receipt
        self.io.perform_candidate=unknown
        result=self.run_loop()
        self.assertEqual(len(self.io.actions),1)
        self.assertEqual(result['stop_reason'],'input_outcome_unknown')
        self.assertFalse(result['verified'])

    def test_f9_during_refinement_does_not_send_a_return(self):
        original=self.io.perform_candidate
        def cancel(*args):
            receipt=original(*args);self.io.cancel=True;return receipt
        self.io.perform_candidate=cancel
        result=self.run_loop()
        self.assertEqual(len(self.io.actions),1)
        self.assertEqual(result['stop_reason'],'interrupted')
        self.assertFalse(result['verified'])


if __name__=='__main__':unittest.main()
