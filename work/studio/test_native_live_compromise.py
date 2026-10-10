"""An unmet goal should position a balanced compromise, without relabeling success."""
from test_support import read_local_fixture_text
from test_support import load_local_palette_session
import copy,importlib,importlib.util,json,unittest
from pathlib import Path
from unittest.mock import patch
from test_native_live_controller import FixtureIO
from native_palette_scoring import score_native_pose,load_session
from native_input_response import replay_native_route,InputSettings,InputGeometry
from native_input_compile import native_drag_gesture
from native_input_route_search import _needed
from native_live.same_session_dye_planner import bind_planning_context,plan_from_checkpoint
from test_support import requires_native_case
from native_palette_search import PoseGrid


class NativeCompromiseTests(unittest.TestCase):
    def setUp(self):
        self.io=FixtureIO()
        fixture=Path(__file__).parent/'fixtures/native_live/user_black'
        requires_native_case(fixture)
        data=json.loads(read_local_fixture_text(fixture/'case.json', encoding='utf-8'))
        self.io.cp=data['initial'];self.io.session=load_local_palette_session(fixture/'palette')
        self.io.settings=InputSettings(**data['settings']);self.io.pose=copy.deepcopy(self.io.cp['pose'])
        self.io.geometry=InputGeometry(self.io.cp['board'],self.io.cp['local_size'],'windows_legacy_mouse_pixels')
        self.rules=[dict(enabled=True,exact=True,colors=['#000000'],tolerance=0) for _ in range(3)]
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('native_live.compromise'),'Compromise policy missing')
        return importlib.import_module('native_live.compromise')
    def context(self):
        c=self.io
        return bind_planning_context(c.session,c.cp,c.geometry,c.settings,wheel_delta_per_step=1.,
            calibration_evidence=dict(source='saved_fixture',viewport_origin=[0,0],viewport_scale=[1,1],
                backend_during_actions_synchronously_recorded=True))
    def row(self,dx,dy):
        c=self.io;gesture=native_drag_gesture(c.geometry,c.settings,dx,dy)
        route=[gesture.record()] if gesture.has_effect else []
        pose=replay_native_route(c.pose,route,c.geometry,c.settings,wheel_delta_per_step=1.,sample_policy='all_recorded_points')['final_pose']
        return dict(input_route=route,final_pose=pose,prediction=score_native_pose(c.session,pose,self.rules),
            needed=_needed(route,3.,.5),source='test_generated_route')
    def test_quality_uses_actual_delta_e_and_balances_all_enabled_regions(self):
        m=self.module()
        a=dict(colors=['#000000']*3,deltas=[1.,2.,50.],predicted_accepted=False,rank=[True,1,1,1])
        b=dict(colors=['#000000']*3,deltas=[15.,15.,15.],predicted_accepted=False,rank=[True,100,3,100])
        self.assertLess(m.predicted_quality(b,self.rules),m.predicted_quality(a,self.rules))
    def test_neighborhood_risk_breaks_an_equal_center_quality_tie(self):
        m=self.module()
        a=dict(colors=['#000000']*3,deltas=[4.,4.,4.],predicted_accepted=False)
        b=dict(colors=['#000000']*3,deltas=[4.,4.,4.],predicted_accepted=False)
        self.assertLess(m.predicted_quality(b,self.rules,landing_maximum=7.),
            m.predicted_quality(a,self.rules,landing_maximum=40.))
    def test_recorded_triple_black_center_quality_beats_a_point_one_five_risk_advantage(self):
        m=self.module()
        from hex_refinement import score_codes
        macro=score_codes(['#000000','#756563','#654865'],self.rules)
        micro=score_codes(['#8F8B68','#596B7F','#536F6B'],self.rules)
        self.assertAlmostEqual(max(macro['deltas']),44.61236,places=4)
        self.assertAlmostEqual(max(micro['deltas']),60.73669,places=4)
        self.assertLess(m.predicted_quality(macro,self.rules,landing_maximum=74.86734008789062),
            m.predicted_quality(micro,self.rules,landing_maximum=74.72117614746094))
    def test_center_average_precedes_uncalibrated_neighborhood_risk(self):
        m=self.module()
        a=dict(colors=['#000000']*3,deltas=[5.,5.,15.],predicted_accepted=False)
        b=dict(colors=['#000000']*3,deltas=[15.,15.,15.],predicted_accepted=False)
        self.assertLess(m.predicted_quality(a,self.rules,landing_maximum=40.),
            m.predicted_quality(b,self.rules,landing_maximum=15.))
    def test_predicted_and_observed_quality_use_the_same_center_order(self):
        m=self.module()
        from hex_refinement import score_codes
        codes=['#000000','#756563','#654865']
        self.assertEqual(m.predicted_quality(score_codes(codes,self.rules),self.rules),
            m.observed_quality(codes,self.rules))
    def test_no_exact_plan_contains_an_audited_compromise_bound_to_the_original_goal(self):
        self.module();c=self.io
        frames=[dict(hex=c.cp['client_hex'],remaining_seconds=None,timer_advisory=True,captured_monotonic=t) for t in (1.,1.1)]
        plan=plan_from_checkpoint(self.context(),c.cp,frames,self.rules,PoseGrid((0,0),(0,0),1,1,(1.,),(0.,)),
            now=1.2,engineering_deadline=61.2,time_budget_seconds=3.)
        self.assertIsNone(plan['candidate'])
        self.assertIsNotNone(plan['compromise_candidate'])
        self.assertFalse(plan['compromise_candidate']['prediction']['predicted_accepted'])
        self.assertTrue(plan['compromise_candidate']['endpoint_audit']['full_route_replayed'])
        self.assertEqual(plan['normalized_rules'],self.rules)
    def test_explicit_compromise_purpose_never_relaxes_the_target_validator(self):
        m=self.module();c=self.io
        frames=[dict(hex=c.cp['client_hex'],remaining_seconds=None,timer_advisory=True,captured_monotonic=t) for t in (1.,1.1)]
        plan=plan_from_checkpoint(self.context(),c.cp,frames,self.rules,PoseGrid((0,0),(0,0),1,1,(1.,),(0.,)),
            now=1.2,engineering_deadline=61.2,time_budget_seconds=3.)
        from native_live.same_session_dye_planner import validate_plan_reference
        fresh=[dict(frame,captured_monotonic=plan['planned_at']+offset) for frame,offset in zip(frames,(.01,.02))]
        with self.assertRaises(ValueError):validate_plan_reference(self.context(),plan,c.cp,fresh,now=plan['planned_at']+.03,rules=self.rules)
        result=validate_plan_reference(self.context(),plan,c.cp,fresh,now=plan['planned_at']+.03,rules=self.rules,purpose='compromise')
        self.assertTrue(result['target_rules_revalidated']);self.assertFalse(result['ready_for_input'])
    def test_fallback_positions_and_reads_actual_colors_instead_of_returning_a_diagnostic(self):
        self.module();c=self.io
        self.rules=[dict(enabled=True,exact=True,colors=['#FF00FF'],tolerance=0.) for _ in range(3)]
        from native_live.controller import run_goal_loop
        result=run_goal_loop(c,c.session,c.settings,self.rules,engineering_deadline=90.,clock=c.clock)
        self.assertEqual(result['stop_reason'],'compromise_observed')
        self.assertEqual(result['outcome'],'compromise');self.assertFalse(result['accepted'])
        self.assertTrue(result['verified'])
        self.assertTrue(result['compromise_selected'])
        self.assertTrue(c.actions)
        self.assertEqual(result['actual_colors'],result['steps'][-1]['after']['client_hex'])
        self.assertLess(result['maximum'],result['initial_maximum'])
        self.assertEqual(len(c.actions),result['actual_input_attempts'])
        self.assertLessEqual(len(c.actions),64)
    def test_expired_compromise_never_sends_input(self):
        m=self.module();c=self.io
        selected=m.choose_compromise(self.context(),c.cp,self.rules,[self.row(0,0),self.row(3,0)],
            deadline=0.,clock=lambda:1.)
        self.assertIsNone(selected)
    def test_no_movement_is_chosen_when_current_color_is_better_than_available_routes(self):
        m=self.module();c=self.io
        selected=m.choose_compromise(self.context(),c.cp,self.rules,[self.row(0,0),self.row(5,-5)],
            deadline=100.,clock=lambda:1.)
        self.assertEqual(selected['input_route'],[])
        self.assertFalse(selected['prediction']['predicted_accepted'])
    def test_neighborhood_sampling_budget_cannot_publish_an_unfinished_audit(self):
        m=self.module();tick=[0.]
        def check():tick[0]+=.2
        selected=m.choose_compromise(self.context(),self.io.cp,self.rules,[self.row(3,0)],
            deadline=.3,clock=lambda:tick[0],check=check)
        self.assertIsNone(selected)
    def test_compromise_rules_and_route_edits_fail_revalidation(self):
        self.module();c=self.io
        frames=[dict(hex=c.cp['client_hex'],remaining_seconds=None,timer_advisory=True,captured_monotonic=t) for t in (1.,1.1)]
        plan=plan_from_checkpoint(self.context(),c.cp,frames,self.rules,PoseGrid((0,0),(0,0),1,1,(1.,),(0.,)),
            now=1.2,engineering_deadline=61.2,time_budget_seconds=3.)
        fresh=[dict(f,captured_monotonic=plan['planned_at']+o) for f,o in zip(frames,(.01,.02))]
        from native_live.same_session_dye_planner import validate_plan_reference
        changed=[dict(r,colors=['#FFFFFF']) for r in self.rules]
        with self.assertRaises(ValueError):
            validate_plan_reference(self.context(),plan,c.cp,fresh,now=plan['planned_at']+.03,rules=changed,purpose='compromise')
        edited=copy.deepcopy(plan);edited['compromise_candidate']['final_pose']['position'][0]+=.001
        with self.assertRaises(ValueError):
            validate_plan_reference(self.context(),edited,c.cp,fresh,now=plan['planned_at']+.03,rules=self.rules,purpose='compromise')
    def test_f9_during_compromise_does_not_submit_a_remaining_predicted_route(self):
        self.module();c=self.io
        from native_live.controller import run_goal_loop
        original=c.perform_candidate
        def action(*args,**kwargs):
            receipt=original(*args,**kwargs);c.cancel=True;return receipt
        c.perform_candidate=action
        result=run_goal_loop(c,c.session,c.settings,self.rules,engineering_deadline=90.,clock=c.clock)
        self.assertEqual(result['stop_reason'],'interrupted');self.assertEqual(len(c.actions),1)
        self.assertFalse(result['verified']);self.assertNotEqual(result['outcome'],'compromise')
    def test_compromise_cannot_start_without_the_whole_remaining_route_budget(self):
        self.module();c=self.io
        self.rules=[dict(enabled=True,exact=True,colors=['#FF00FF'],tolerance=0.) for _ in range(3)]
        from native_live.controller import run_goal_loop
        result=run_goal_loop(c,c.session,c.settings,self.rules,engineering_deadline=90.,clock=c.clock,max_actions=1)
        self.assertEqual(c.actions,[])
        self.assertEqual(result['stop_reason'],'insufficient_compromise_actions')
        self.assertNotEqual(result['outcome'],'compromise')
    def test_better_measured_intermediate_is_restored_after_a_worse_final_pose(self):
        self.module();c=self.io
        from native_live.controller import run_goal_loop
        from native_live.same_session_dye_planner import _plan_fingerprint,_json
        import hashlib
        first=self.row(5,0)['input_route'][0]
        second=native_drag_gesture(c.geometry,c.settings,-5,0).record()
        def forced(*args,**kw):
            context,cp,frames,rules,grid=args
            actual=[dict(enabled=True,exact=True,colors=[color],tolerance=0.) for color in cp['client_hex']]
            plan=plan_from_checkpoint(context,cp,frames,actual,grid,**kw)
            route=[first,second];pose=replay_native_route(cp['pose'],route,c.geometry,c.settings,
                wheel_delta_per_step=1.,sample_policy='all_recorded_points')['final_pose']
            row=dict(input_route=route,final_pose=pose,prediction=score_native_pose(c.session,pose,rules),
                needed=_needed(route,3.,.5),source='test_worse_final_route')
            plan.update(candidate=None,compromise_candidate=row,normalized_rules=rules,
                rules_fingerprint=hashlib.sha256(_json(rules).encode()).hexdigest(),result_classification='not_found_in_budget')
            plan['plan_fingerprint']=_plan_fingerprint(plan);return plan
        result=run_goal_loop(c,c.session,c.settings,self.rules,engineering_deadline=90.,clock=c.clock,planner=forced)
        self.assertTrue(result['best_current'])
        self.assertLess(result['maximum'],result['initial_maximum'])
        # Optional protected refinement follows restoration. The original
        # positioning/restore phase itself still has at most four inputs.
        original_steps=[s for s in result['steps'] if s['purpose'] not in ('refine','restore_refinement')]
        self.assertGreater(len(original_steps),2);self.assertLessEqual(len(original_steps),4)
        self.assertLessEqual(len(c.actions),64)
        self.assertEqual(result['stop_reason'],'compromise_observed')


if __name__=='__main__':unittest.main()
