"""Finishing CPU search cannot erase a fully audited, executable short route."""
import copy
import unittest
from unittest.mock import patch

from input_gestures import PointerGesture
from native_input_response import replay_native_route
from native_palette_scoring import score_native_pose
from native_palette_search import PoseGrid
from native_live.same_session_dye_planner import bind_planning_context, plan_from_checkpoint
from native_live.compromise import predicted_quality
from test_native_retry import RetryIO


class PlannerCandidateBudgetTests(unittest.TestCase):
    def setUp(self):
        self.io = RetryIO()
        self.cp = self.io.checkpoint('initial', 200.)
        self.frames = self.io.frames('initial', 200.)
        self.start = self.io.t
        self.route = [PointerGesture('drag', ((260, 260), (270, 260))).record()]
        self.final = replay_native_route(self.cp['pose'], self.route, self.io.geometry, self.io.settings,
            wheel_delta_per_step=1., sample_policy='all_recorded_points')['final_pose']
        prediction = score_native_pose(self.io.session, self.final, self.io.neutral)
        self.rules = [dict(enabled=True, exact=True, colors=[color], tolerance=0.) for color in prediction['colors']]
        self.context = bind_planning_context(self.io.session, self.cp, self.io.geometry, self.io.settings,
            wheel_delta_per_step=1., calibration_evidence=dict(source='independent-offline-drag',
                viewport_origin=[0, 0], viewport_scale=[1., 1.], backend_during_actions_synchronously_recorded=True))
        self.periodic = dict(candidates=[dict(native_pose=self.final)], nearest_candidates=[], enabled_regions=[0, 1, 2])
        self.grid = PoseGrid((0, 0), (0, 0), 1, 1, (1.,), (0.,))

    def compile(self, *args, **options):
        self.offered = options['time_budget_seconds']
        self.io.t = self.start + self.cost
        return dict(input_route=copy.deepcopy(self.route), final_pose=copy.deepcopy(self.final))

    def plan(self, *, cpu_cost=2.05, search_budget=2., deadline=90.):
        self.cost = cpu_cost
        with patch('native_live.same_session_dye_planner.search_periodic_targets', return_value=self.periodic), \
             patch('native_live.same_session_dye_planner.compile_periodic_approach', side_effect=self.compile):
            return plan_from_checkpoint(self.context, self.cp, self.frames, self.rules, self.grid,
                now=self.start, engineering_deadline=deadline, time_budget_seconds=search_budget,
                clock=self.io.clock)

    def test_audited_candidate_survives_search_cap_when_complete_route_still_fits(self):
        result = self.plan()
        self.assertIsNotNone(result['candidate'], result['stop_reason'])
        self.assertEqual(result['candidate']['input_route'], self.route)
        self.assertTrue(result['candidate']['endpoint_audit']['full_route_replayed'])
        self.assertFalse(result['candidate']['execution_verified'])
        self.assertTrue(result['search_budget_exhausted'])

    def test_no_candidate_is_admitted_when_its_real_route_and_reference_do_not_fit(self):
        result = self.plan(deadline=self.start + 5.)
        self.assertIsNone(result['candidate'])
        self.assertEqual(result['result_classification'], 'insufficient_time')
        self.assertFalse(result['ready_for_input'])

    def test_promising_global_target_gets_time_to_finish_before_another_target(self):
        self.plan(cpu_cost=.1, search_budget=12.)
        self.assertGreaterEqual(self.offered, 2.5)

    def test_finished_search_retains_an_audited_compromise_without_starting_more_search(self):
        self.rules = [dict(enabled=True, exact=True, colors=['#FFFFFF'], tolerance=0.) for _ in range(3)]
        self.periodic = dict(candidates=[], nearest_candidates=[dict(native_pose=self.final)], enabled_regions=[0, 1, 2])
        self.cost = 2.05
        with patch('native_live.same_session_dye_planner.search_periodic_targets', return_value=self.periodic), \
             patch('native_live.same_session_dye_planner.compile_periodic_approach', side_effect=self.compile), \
             patch('native_live.same_session_dye_planner.search_native_input_pipeline') as pipeline:
            pipeline.return_value = dict(candidates=[])
            result = plan_from_checkpoint(self.context, self.cp, self.frames, self.rules, self.grid,
                now=self.start, engineering_deadline=90., time_budget_seconds=2., clock=self.io.clock)
        self.assertIsNotNone(result['compromise_candidate'], result['stop_reason'])
        self.assertTrue(result['compromise_candidate']['endpoint_audit']['full_route_replayed'])
        self.assertFalse(result['compromise_candidate']['execution_verified'])
        self.assertTrue(result['search_budget_exhausted'])
        pipeline.assert_not_called()

    def test_a_shorter_feasible_compromise_is_kept_when_the_best_long_route_does_not_fit(self):
        self.rules = [dict(enabled=True, exact=True, colors=['#FFFFFF'], tolerance=0.) for _ in range(3)]
        short = [PointerGesture('drag', ((260, 260), (270, 260))).record()]
        long = short * 8
        endpoints = []
        for route in (long, short):
            pose = replay_native_route(self.cp['pose'], route, self.io.geometry, self.io.settings,
                wheel_delta_per_step=1., sample_policy='all_recorded_points')['final_pose']
            endpoints.append((route, pose, score_native_pose(self.io.session, pose, self.rules)))
        # The test controls route feasibility below; ranking is intentionally
        # independent of which proposal was generated first.
        periodic = dict(candidates=[], nearest_candidates=[dict(native_pose=pose) for _, pose, _ in endpoints],
                        enabled_regions=[0, 1, 2])
        def compile(target, *args, **options):
            self.io.t = self.start + .1
            route, pose, _ = next(row for row in endpoints if row[1] == target)
            return dict(input_route=copy.deepcopy(route), final_pose=copy.deepcopy(pose))
        with patch('native_live.same_session_dye_planner.search_periodic_targets', return_value=periodic), \
             patch('native_live.same_session_dye_planner.compile_periodic_approach', side_effect=compile), \
             patch('native_live.same_session_dye_planner.search_native_input_pipeline', return_value=dict(candidates=[])):
            result = plan_from_checkpoint(self.context, self.cp, self.frames, self.rules, self.grid,
                now=self.start, engineering_deadline=self.start + 12., time_budget_seconds=8., clock=self.io.clock)
        self.assertIsNotNone(result['compromise_candidate'], result['stop_reason'])
        self.assertIn(result['compromise_candidate']['input_route'], (short, []))
        self.assertFalse(result['ready_for_input'])


if __name__ == '__main__':
    unittest.main()
