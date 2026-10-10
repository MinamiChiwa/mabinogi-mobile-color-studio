"""Synthetic actual two-fragment boards; no live-game authenticity claims."""
import copy
import hashlib
import json
import tempfile
import time
import unittest
from unittest.mock import patch
from dataclasses import asdict
from pathlib import Path

import numpy as np
from PIL import Image

from hex_refinement import score_codes
from native_input_compile import compile_native_route, native_drag_gesture
from native_input_response import InputGeometry, InputSettings, replay_native_route, _pose
from native_palette_scoring import load_session, score_native_pose
from native_palette_search import PoseGrid, search_pose_grid
from native_live.controller import run_goal_loop
from native_live.same_session_dye_planner import (
    _checked_checkpoint, bind_planning_context, plan_from_checkpoint,
)


INITIAL = ['#BE2233', '#3F4455']
MOVED = ['#BD2233', '#3E4455']


def rules_for(codes, **extra):
    return [dict(enabled=True, exact=True, colors=[c], tolerance=0., **extra) for c in codes]


def two_session():
    x = np.arange(254, dtype=np.uint8)
    pixels = tuple(np.broadcast_to(np.stack((x, np.full(254, g, np.uint8),
        np.full(254, b, np.uint8)), axis=-1), (254, 254, 3)).copy()
        for g, b in ((34, 51), (68, 85)))
    return dict(pixels=pixels, picker_uv=[[.25, .5], [.75, .5]],
        color_preserve_ratio=0., initial_pose=dict(position=[0., 0.], scale=1., rotation_degrees=0.),
        source='synthetic_two_fragment_test', capture_id='synthetic-two')


class SyntheticTwoIO:
    def __init__(self):
        self.session = two_session()
        self.settings = InputSettings(.65, 1.5, 0., .0001, .05)
        self.geometry = InputGeometry((100, 100, 600, 600), (500, 500), 'windows_legacy_mouse_pixels')
        self.pose = copy.deepcopy(self.session['initial_pose'])
        self.t = 1.
        self._clock_at = time.monotonic()
        self.actions = []
        self.releases = 0
        self.binding = json.dumps([['synthetic-two'], [123, 456, 789, 'synthetic-build'],
            {'synthetic_motion': True}, asdict(self.settings), {'window': {'hwnd': 20}}])

    def clock(self):
        now = time.monotonic()
        self.t += now - self._clock_at
        self._clock_at = now
        return self.t

    def check(self, deadline):
        if self.clock() >= deadline:
            raise TimeoutError('synthetic deadline')

    def planning_check(self, deadline):
        self.check(deadline)

    def input_backend(self, deadline):
        self.check(deadline)
        return dict(process_identity=json.loads(self.binding)[1], backend_object='synthetic',
            backend_type='MM.Client.Framework.InputSystem.InputManager', input_assistant='0x0',
            legacy_mouse_getter_rva='0x185310', viewport_origin=[0, 0], viewport_scale=[1., 1.])

    def checkpoint(self, label, deadline):
        self.check(deadline)
        codes = score_native_pose(self.session, self.pose, rules_for(['#000000'] * 2))['colors']
        return dict(checkpoint_valid=True, cpu_matches=True, label=label, pose=_pose(self.pose),
            client_hex=codes, binding=self.binding, board=list(self.geometry.board),
            local_size=list(self.geometry.local_size))

    def frames(self, label, deadline):
        cp = self.checkpoint(label, deadline)
        when = self.clock()
        return [dict(hex=cp['client_hex'], remaining_seconds=None, timer_advisory=True,
            captured_monotonic=when + offset) for offset in (-.001, 0.)]

    def perform_candidate(self, record, label, deadline):
        self.check(deadline)
        self.actions.append(copy.deepcopy(record))
        self.pose = replay_native_route(self.pose, [record], self.geometry, self.settings,
            wheel_delta_per_step=1., sample_policy='all_recorded_points')['final_pose']
        return dict(completed=True, input_source='explicit_synthetic_simulation', gesture=record,
            actual_trace=[dict(actual_client=list(p)) for p in record['points']])

    def release(self):
        self.releases += 1

    def context(self):
        return bind_planning_context(self.session, self.checkpoint('baseline', 100.),
            self.geometry, self.settings, wheel_delta_per_step=1., calibration_evidence=dict(
                source='explicit_synthetic_test', viewport_origin=[0, 0], viewport_scale=[1., 1.],
                backend_during_actions_synchronously_recorded=False))


class TwoRegionTests(unittest.TestCase):
    def call(self, fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ValueError as exc:
            self.fail(str(exc))

    def test_actual_two_centers_use_two_in_the_cpu_picker(self):
        session = two_session()
        scored = self.call(score_native_pose, session, session['initial_pose'], rules_for(INITIAL))
        self.assertEqual(scored['colors'], INITIAL)
        self.assertTrue(scored['predicted_accepted'])
        self.assertFalse(scored['verified'])

    def test_exact_alternatives_similar_disabled_and_ui_priority_order(self):
        rules = rules_for(INITIAL)
        rules[0].update(colors=['#FFFFFF', INITIAL[0]], priority=3)
        rules[1].update(exact=False, colors=['#404455'], tolerance=5., priority=1)
        result = self.call(score_codes, INITIAL, rules)
        self.assertTrue(result['accepted'])
        self.assertFalse(result['target_exact'])
        self.assertEqual(len(result['deltas']), 2)
        rules[1].update(enabled=False, colors=[])
        result = self.call(score_codes, [INITIAL[0], None], rules)
        self.assertTrue(result['accepted'])
        self.assertIsNone(result['deltas'][1])

    def test_load_actual_two_fragments_keeps_the_real_layout(self):
        session = two_session()
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            fragments = []
            for i, pixels in enumerate(session['pixels']):
                name = 'fragment_%d.png' % i
                Image.fromarray(pixels).save(folder / name)
                fragments.append(dict(index=i, width=254, height=254, channels=3,
                    normalized_picker_y=.5, pixel_file=name,
                    raw_sha256=hashlib.sha256(pixels[::-1].tobytes()).hexdigest()))
            record = dict(session['initial_pose'], state_stable_during_read=True,
                color_preserve_ratio=0., fragments=fragments)
            (folder / 'snapshot.json').write_text(json.dumps(record), encoding='utf-8')
            loaded = self.call(load_session, folder)
            self.assertEqual(loaded['picker_uv'], [[.25, .5], [.75, .5]])
            self.assertEqual(score_native_pose(loaded, loaded['initial_pose'], rules_for(INITIAL))['colors'], INITIAL)

    def test_two_region_grid_and_compiler_score_all_real_markers(self):
        io = SyntheticTwoIO()
        result = self.call(search_pose_grid, io.session,
            PoseGrid((0., 0.), (0., 0.), 1, 1, (1.,), (0.,)), rules_for(INITIAL), max_candidates=1)
        self.assertEqual(result['predicted_accepted_count'], 1)
        target = dict(position=[.04, 0.], scale=1., rotation_degrees=0.)
        compiled = self.call(compile_native_route, target, io.pose, io.geometry, io.settings,
            [(225., 350.), (475., 350.)], wheel_delta_per_step=1., sample_policy='all_recorded_points',
            now=1., deadline=90., planning_seconds=1.)
        self.assertEqual(len(compiled['marker_errors']), 2)
        self.assertTrue(compiled['input_route'])
        self.assertLess(max(compiled['marker_errors']), .1)

    def test_production_planner_and_controller_reach_a_two_color_goal(self):
        io = SyntheticTwoIO()
        result = self.call(run_goal_loop, io, io.session, io.settings, rules_for(MOVED),
            engineering_deadline=90., clock=io.clock, max_rounds=2)
        self.assertTrue(result['accepted'], result.get('error'))
        self.assertEqual(result['actual_colors'], MOVED)
        self.assertEqual(len(result['actual_deltas']), 2)
        self.assertTrue(io.actions)
        self.assertFalse(result['server_confirmation_verified'])

    def test_actual_two_ui_rules_ignore_the_absent_third_without_mutation(self):
        io = SyntheticTwoIO()
        ui_rules = rules_for(INITIAL + ['#FFFFFF'])
        ui_rules[0]['priority'] = 3
        ui_rules[1]['priority'] = 1
        ui_rules[2]['priority'] = 2
        before = copy.deepcopy(ui_rules)
        result = self.call(run_goal_loop, io, io.session, io.settings, ui_rules,
            engineering_deadline=90., clock=io.clock)
        self.assertTrue(result['accepted'], result.get('error'))
        self.assertEqual(len(result['rules']), 2)
        self.assertEqual(ui_rules, before)
        self.assertEqual(io.actions, [])

    def test_bound_checkpoint_cannot_gain_a_third_region(self):
        io = SyntheticTwoIO()
        context = self.call(io.context)
        cp = io.checkpoint('changed', 100.)
        cp['client_hex'].append('#FFFFFF')
        with self.assertRaises(ValueError):
            _checked_checkpoint(context, cp)
        changed = copy.deepcopy(context)
        changed['session']['pixels'] += (np.zeros((254, 254, 3), np.uint8),)
        changed['session']['picker_uv'].append([5 / 6, .5])
        with self.assertRaises(ValueError):
            _checked_checkpoint(changed, io.checkpoint('same', 100.))

    def test_production_recovery_returns_to_both_observed_colors(self):
        from native_live.refinement import find_recovery, _endpoint_checkpoint
        io = SyntheticTwoIO()
        baseline = self.call(io.checkpoint, 'baseline', 100.)
        context = self.call(io.context)
        io.pose = dict(position=[.04, 0.], scale=1., rotation_degrees=0.)
        actual = io.checkpoint('actual', 100.)
        generated = self.call(_endpoint_checkpoint, context, baseline, io.pose, lambda: None)
        self.assertEqual(generated['client_hex'], MOVED)
        back = native_drag_gesture(io.geometry, io.settings, -20, 0).record()
        recovery = self.call(find_recovery, context, actual, baseline, rules_for(INITIAL),
            deadline=io.clock() + 5., clock=io.clock, preferred_routes=([back],))
        self.assertIsNotNone(recovery)
        self.assertEqual(recovery['prediction']['colors'], INITIAL)
        self.assertFalse(recovery['ready_for_input'])

    def test_closed_loop_restores_two_observed_colors_after_actual_drift(self):
        from native_input_route_search import _needed
        from native_live.same_session_dye_planner import audit_candidate_endpoint, _plan_fingerprint, _json
        io = SyntheticTwoIO()
        io.pose = dict(position=[.04, 0.], scale=1., rotation_degrees=0.)
        rules = rules_for(['#000000', '#000000'])
        original = io.perform_candidate
        def drift_once(record, label, deadline):
            receipt = original(record, label, deadline)
            if len(io.actions) == 1:
                io.pose = copy.deepcopy(io.session['initial_pose'])
            return receipt
        io.perform_candidate = drift_once
        def compromised_plan(context, cp, frames, received, grid, **kw):
            route = [native_drag_gesture(io.geometry, io.settings, 5, 0).record()]
            endpoint = replay_native_route(cp['pose'], route, io.geometry, io.settings,
                wheel_delta_per_step=1., sample_policy='all_recorded_points')['final_pose']
            row = audit_candidate_endpoint(context, cp, received, dict(input_route=route,
                final_pose=endpoint, prediction=score_native_pose(io.session, endpoint, received),
                needed=_needed(route, 3., .5), source='explicit_synthetic_compromise'))
            plan = dict(schema=4, context_fingerprint=context['fingerprint'], reference_pose=cp['pose'],
                reference_frame_monotonic=frames[-1]['captured_monotonic'], planned_at=io.clock(),
                effective_deadline=kw['engineering_deadline'], candidate=None, approach_candidate=None,
                compromise_candidate=row, reserve_seconds=10., verification_margin_seconds=8.,
                normalized_rules=received, rules_fingerprint=hashlib.sha256(_json(received).encode()).hexdigest(),
                result_classification='not_found_in_budget', nearest_diagnostic=None,
                reachability_conclusion='not_established')
            plan['plan_fingerprint'] = _plan_fingerprint(plan)
            return plan
        with patch('native_live.controller.find_refinement', return_value=None):
            result = self.call(run_goal_loop, io, io.session, io.settings, rules,
                engineering_deadline=90., clock=io.clock, planner=compromised_plan)
        self.assertTrue(result['restored'], result.get('error'))
        self.assertTrue(result['best_current'])
        self.assertEqual(result['actual_colors'], MOVED)
        self.assertGreaterEqual(len(io.actions), 2)
        self.assertEqual(len(result['actual_deltas']), 2)
        self.assertTrue(all(len(row['checkpoint']['client_hex']) == 2 for row in result['observations']))
        self.assertFalse(result['accepted'])
        self.assertFalse(result['server_confirmation_verified'])

    def test_joint_periodic_search_and_target_seeds_use_actual_two_geometry(self):
        from native_periodic_search import search_periodic_targets
        from native_target_seeds import target_seed_poses
        a = np.full((32, 32, 3), 180, np.uint8)
        b = a.copy()
        a[11, 25] = 0
        b[12, 5] = 0
        session = dict(two_session(), pixels=(a, b), picker_uv=[[.25, .25], [.75, .26]])
        rules = rules_for(['#000000', '#000000'])
        result = self.call(search_periodic_targets, session, rules, minimum_scale=.5, maximum_scale=3.)
        self.assertTrue(result['candidates'])
        self.assertEqual(len(result['target_sites_per_region']), 2)
        self.assertTrue(all(row['prediction']['colors'] == ['#000000', '#000000']
            for row in result['candidates']))
        self.assertFalse(result['continuous_complete'])
        seeds = self.call(target_seed_poses, session, rules, pixels_per_region=1, max_candidates=4)
        self.assertTrue(seeds['poses'])
        self.assertEqual({row['anchor_region'] for row in seeds['seeds']}, {0, 1})

    def test_input_pipeline_and_route_search_keep_two_predictions(self):
        from native_input_pipeline import search_native_input_pipeline, bind_native_route_seeds
        from native_input_route_search import search_native_input_routes
        io = SyntheticTwoIO()
        rules = rules_for(INITIAL)
        routes = self.call(search_native_input_routes, io.session, [[]], io.pose, io.geometry,
            io.settings, rules, wheel_delta_per_step=1., sample_policy='all_recorded_points',
            now=1., deadline=90., max_depth=0)
        self.assertTrue(routes['candidates'])
        self.assertEqual(routes['candidates'][0]['prediction']['colors'], INITIAL)
        bundle = bind_native_route_seeds(io.session, io.geometry, io.settings, [[]],
            wheel_delta_per_step=1., sample_policy='all_recorded_points')
        grid = PoseGrid((0., 0.), (0., 0.), 1, 1, (1.,), (0.,))
        result = self.call(search_native_input_pipeline, io.session, grid, io.geometry, io.settings,
            rules, wheel_delta_per_step=1., sample_policy='all_recorded_points', now=1., deadline=90.,
            seed_bundle=bundle, generate_target_seeds=False, max_coarse=1, max_structural=1,
            macro_candidates=1, pivot_candidates=1)
        self.assertTrue(result['candidates'])
        self.assertEqual(result['candidates'][0]['prediction']['colors'], INITIAL)

    def test_runtime_observation_rejects_region_count_changes(self):
        from native_runtime_observation import validate_observation, validate_stable_pair
        record = dict(active=True, build_sha256='a' * 64, pid=123, process_creation_token=99,
            capture_id='synthetic-two', session_token='synthetic-session', pixel_sha256=['b' * 64, 'c' * 64],
            region_count=2, pose=dict(position=[0., 0.], scale=1., rotation_degrees=0.),
            animator=dict(position=dict(is_done=True, stop_requested=False, elapsed=0., duration=0.,
                last=[0., 0.], target=[0., 0.]), rotation=dict(is_done=True, stop_requested=False,
                elapsed=0., duration=0., last=0., target=0.)),
            geometry=dict(board=[100., 100., 600., 600.], local_size=[500., 500.], camera='null',
                source='runtime_recttransform'), settings=asdict(SyntheticTwoIO().settings),
            scroll=dict(project_delta=1., game_delta=1., sign_verified=True, observed_events=1),
            monotonic_time=1.)
        first = self.call(validate_observation, record)
        self.assertEqual(len(first['pixel_sha256']), 2)
        second = dict(record, monotonic_time=1.2)
        self.assertTrue(self.call(validate_stable_pair, record, second)['stable'])
        with self.assertRaises(ValueError):
            validate_observation(dict(record, region_count=3))
        second.update(region_count=3, pixel_sha256=[*record['pixel_sha256'], 'd' * 64])
        with self.assertRaises(ValueError):
            validate_stable_pair(record, second)


if __name__ == '__main__':
    unittest.main()
