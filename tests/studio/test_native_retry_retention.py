"""A retry owns the previous measured result until a better result is verified."""
import copy,inspect,unittest
from unittest.mock import patch

import test_native_retry as fixtures
from input_gestures import drag_gesture
from native_input_response import replay_native_route
from native_input_route_search import _needed
from native_palette_scoring import score_native_pose
from native_live.same_session_dye_planner import audit_candidate_endpoint


class RetryRetentionTests(unittest.TestCase):
    def test_dropped_reset_notch_cannot_consume_the_return_action_allowance(self):
        from test_native_retry_continuous import ContinuousRetryIO
        from input_gestures import PointerGesture
        io=ContinuousRetryIO();runner=fixtures.NativeRetryTests()
        original=io.perform_retry_reset;start=copy.deepcopy(io.pose);first=[True]
        def dropped(route,label,deadline):
            receipt=original(route,label,deadline)
            if first[0]:
                first[0]=False;short=copy.deepcopy(route);last=short[-1]
                short[-1]=PointerGesture('wheel',tuple(map(tuple,last['points'])),wheel_steps=last['wheel_steps']+1).record()
                io.pose=replay_native_route(start,short,io.geometry,io.settings,
                    wheel_delta_per_step=1.,sample_policy='all_recorded_points')['final_pose']
            return receipt
        io.perform_retry_reset=dropped
        requested,event,events=runner.once_ready(io,retry_at=34.)
        result=runner.run_loop(io,requested,event,max_actions=7)
        self.assertTrue(result['best_current'],result.get('retries'))
        self.assertLessEqual(len(io.actions),7)
        self.assertEqual(len([s for s in result['steps'] if s['purpose']=='retry_reset']),1)

    def test_reset_is_not_started_when_action_quota_cannot_cover_return(self):
        from test_native_retry_continuous import ContinuousRetryIO
        io=ContinuousRetryIO();runner=fixtures.NativeRetryTests()
        requested,event,events=runner.once_ready(io,retry_at=34.)
        old=io.colors()
        result=runner.run_loop(io,requested,event,max_actions=2)
        self.assertEqual(io.actions,[],result.get('retries'))
        self.assertEqual(result['actual_colors'],old)
        self.assertTrue(result['best_current'])
        self.assertEqual(result['retries'][0]['reason'],'insufficient_retry_actions')

    def test_full_search_leaves_room_for_return_preparation(self):
        from test_native_retry_continuous import ContinuousRetryIO
        import native_live.controller as controller
        io=ContinuousRetryIO();runner=fixtures.NativeRetryTests()
        requested,event,events=runner.once_ready(io,retry_at=60.)
        prepare=controller.prepare_retry_recovery
        def slow_return(*args,**kwargs):
            row=prepare(*args,**kwargs)
            if kwargs.get('preferred_routes'):io.t+=1.9
            return row
        def planner(*args,**kwargs):
            io.t+=kwargs['time_budget_seconds']
            return dict(candidate=None,compromise_candidate=None,effective_deadline=kwargs['engineering_deadline'],
                result_classification='not_found_in_budget')
        with patch.object(controller,'prepare_retry_recovery',side_effect=slow_return):
            result=runner.run_loop(io,requested,event,planner=planner)
        self.assertTrue(result.get('retry_recovered'),result.get('retries'))
        self.assertTrue(result['best_current'])

    def test_full_search_budget_still_leaves_time_for_measured_return(self):
        io=fixtures.RetryIO();runner=fixtures.NativeRetryTests()
        checkpoint=io.checkpoint;frames=io.frames;perform=io.perform_candidate
        def native(label,deadline):io.t+=1.2;return checkpoint(label,deadline)
        def visual(label,deadline):io.t+=2.3;return frames(label,deadline)
        def send(record,label,deadline):io.t+=.35;return perform(record,label,deadline)
        io.checkpoint=native;io.frames=visual;io.perform_candidate=send
        requested,event,events=runner.once_ready(io,retry_at=40.)
        plans=[]
        def planner(*args,**kwargs):
            plans.append(kwargs['time_budget_seconds']);io.t+=kwargs['time_budget_seconds']
            return dict(candidate=None,compromise_candidate=None,effective_deadline=kwargs['engineering_deadline'],
                result_classification='not_found_in_budget')
        result=runner.run_loop(io,requested,event,planner=planner,deadline=100.)
        self.assertTrue(result.get('retry_recovered'),result.get('retries'))
        self.assertTrue(result['best_current']);self.assertLess(io.t,100.)
        self.assertEqual(len(plans),1)

    def test_failed_post_reset_search_restores_previous_measured_result(self):
        io=fixtures.RetryIO()
        runner=fixtures.NativeRetryTests();requested,event,events=runner.once_ready(io,retry_at=34.)
        old_colors=io.colors();old_pose=copy.deepcopy(io.pose)
        result=runner.run_loop(io,requested,event)
        self.assertEqual(result['retry_epochs'],1,result.get('error'))
        self.assertEqual(result['actual_colors'],old_colors)
        self.assertEqual(result['best_actual_colors'],old_colors)
        self.assertTrue(result['best_current']);self.assertTrue(result['screenshot_verified'])
        restored=[s for s in result['steps'] if s['purpose']=='restore_retry']
        self.assertTrue(restored)
        self.assertEqual(result['retries'][0]['recovery']['status'],'restored')
        self.assertGreater(io.pose['scale'],.5)
        self.assertEqual(io.releases,1)

    def test_retry_keeps_original_rules_when_restoring_mixed_priorities(self):
        io=fixtures.RetryIO()
        io.rules[0].update(exact=False,tolerance=8.,priority=2)
        io.rules[1].update(priority=1)
        io.rules[2].update(enabled=False,colors=[],priority=3)
        runner=fixtures.NativeRetryTests();requested,event,events=runner.once_ready(io,retry_at=34.)
        result=runner.run_loop(io,requested,event)
        self.assertEqual(result['rules'][0]['tolerance'],8.)
        self.assertEqual(result['rules'][1]['priority'],1)
        self.assertFalse(result['rules'][2]['enabled'])
        self.assertTrue(result['best_current'])
        self.assertEqual(result['actual_colors'][:2],result['initial']['checkpoint']['client_hex'][:2])

    def test_f9_during_return_never_sends_another_action_or_claims_restored(self):
        io=fixtures.RetryIO();runner=fixtures.NativeRetryTests();requested,event,events=runner.once_ready(io,retry_at=34.)
        original=io.perform_candidate
        def perform(record,label,deadline):
            receipt=original(record,label,deadline)
            if label.startswith('retry_return_'):io.cancel=True
            return receipt
        io.perform_candidate=perform
        result=runner.run_loop(io,requested,event)
        self.assertEqual(result['stop_reason'],'interrupted')
        returns=[s for s in result['steps'] if s['purpose']=='restore_retry']
        self.assertEqual(len(returns),1)
        self.assertFalse(result['verified']);self.assertFalse(result.get('restored',False))


class MeasuredPlannerAdmissionTests(unittest.TestCase):
    def test_unaffordable_exact_route_continues_to_next_exact_route(self):
        import native_live.same_session_dye_planner as planner
        import test_native_planner_tail as fixture
        from native_input_response import InputGeometry
        case=fixture.PlannerTailTests();case.setUp()
        geometry=InputGeometry(case.context['board'],case.context['local_size'],'windows_legacy_mouse_pixels')
        routes=[[drag_gesture(geometry.board,10,0).record()]*2,[drag_gesture(geometry.board,5,0).record()]]
        endpoints=[score_native_pose(case.session,replay_native_route(case.cp['pose'],route,geometry,case.settings,
            wheel_delta_per_step=1.,sample_policy='all_recorded_points')['final_pose'],
            [dict(enabled=True,exact=True,colors=['#000000'],tolerance=0.) for _ in range(3)])['colors'] for route in routes]
        rules=[dict(enabled=i<2,exact=True,colors=list({p[i] for p in endpoints}),tolerance=0.) for i in range(3)]
        with patch.object(planner,'search_periodic_targets',return_value=dict(candidates=[],nearest_candidates=[])),\
            patch.object(planner,'_local_input_candidates',return_value=[('fresh_local_integer_drag',r) for r in routes]):
            result=planner.plan_from_checkpoint(case.context,case.cp,case.frames,rules,case.grid,
                now=100.2,engineering_deadline=200.,time_budget_seconds=6.,clock=lambda:100.2,
                candidate_admission=lambda row:len(row['input_route'])<=1)
        self.assertIsNotNone(result['candidate'])
        self.assertEqual(result['candidate']['input_route'],routes[1])

    def test_unaffordable_best_miss_does_not_hide_an_affordable_improvement(self):
        import native_live.same_session_dye_planner as planner
        import test_native_planner_tail as fixture
        case=fixture.PlannerTailTests();case.setUp()
        rules=[dict(enabled=True,exact=True,colors=['#000000'],tolerance=0.) for _ in range(3)]
        g=case.context
        from native_input_response import InputGeometry,InputSettings
        geometry=InputGeometry(g['board'],g['local_size'],'windows_legacy_mouse_pixels')
        # The ranking/auditing remains real. The test injects finite generated
        # routes only, to isolate the live-cost admission contract.
        routes=[('fresh_local_integer_drag',[drag_gesture(geometry.board,dx,dy).record()])
                for dx,dy in ((0,5),(-1,0),(0,-1))]
        rows=[]
        for _,route in routes:
            pose=replay_native_route(case.cp['pose'],route,geometry,case.settings,
                wheel_delta_per_step=1.,sample_policy='all_recorded_points')['final_pose']
            from native_live.compromise import predicted_quality
            rows.append(dict(route=route,quality=predicted_quality(score_native_pose(case.session,pose,rules),rules)))
        rows.sort(key=lambda row:row['quality'])
        cheapest=rows[1]['route'];rejected=rows[0]['route'];calls=[]
        def admission(row):
            calls.append(copy.deepcopy(row['input_route']))
            return row['input_route']!=rejected
        self.assertIn('candidate_admission',inspect.signature(planner.plan_from_checkpoint).parameters)
        with patch.object(planner,'search_periodic_targets',return_value=dict(candidates=[],nearest_candidates=[])),\
            patch.object(planner,'_local_input_candidates',return_value=[('fresh_local_integer_drag',row['route']) for row in rows]),\
            patch.object(planner,'search_native_input_pipeline',return_value={'candidates':[]}),\
            patch.object(planner,'_refine_single_wheels',return_value={'candidates':[]}):
            result=planner.plan_from_checkpoint(case.context,case.cp,case.frames,rules,case.grid,
                now=100.2,engineering_deadline=200.,time_budget_seconds=6.,clock=lambda:100.2,
                candidate_admission=admission)
        self.assertIn(rejected,calls)
        self.assertEqual(result['compromise_candidate']['input_route'],cheapest)


if __name__=='__main__':unittest.main()
