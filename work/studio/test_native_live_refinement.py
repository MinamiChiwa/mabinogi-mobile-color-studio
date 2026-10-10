"""Protected local proposals use real native replay and strict target scoring."""
from test_support import read_local_fixture_text
from test_support import load_local_palette_session
import copy
import importlib
import importlib.util
import json
import time
import unittest
from pathlib import Path

from native_input_compile import native_drag_gesture
from native_input_response import InputGeometry, InputSettings, replay_native_route
from native_palette_scoring import load_session, score_native_pose
from native_live.compromise import observed_quality, predicted_quality
from native_live.same_session_dye_planner import bind_planning_context, audit_candidate_endpoint
from test_native_live_controller import FixtureIO


class ProtectedRefinementTests(unittest.TestCase):
    def setUp(self):
        self.io = FixtureIO()
        self.rules = self.io.case['rules']

    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('native_live.refinement'),
                             'Protected local refinement module is missing')
        return importlib.import_module('native_live.refinement')

    def context(self):
        c = self.io
        return bind_planning_context(c.session, c.cp, c.geometry, c.settings,
            wheel_delta_per_step=1., calibration_evidence=dict(source='offline_test',
            viewport_origin=[0, 0], viewport_scale=[1, 1],
            backend_during_actions_synchronously_recorded=True))

    def checkpoint_at(self, pose):
        cp = copy.deepcopy(self.io.cp)
        neutral = [dict(enabled=True, exact=True, colors=['#000000'], tolerance=0.)] * 3
        cp.update(pose=pose, client_hex=score_native_pose(self.io.session, pose, neutral)['colors'])
        return cp

    def test_improving_trial_has_an_audited_return_for_every_prefix(self):
        m = self.module()
        context = self.context()
        row = m.find_refinement(context, self.io.cp, self.rules,
            deadline=time.monotonic()+2., radius_pixels=1)
        self.assertIsNotNone(row)
        self.assertLess(predicted_quality(row['prediction'], self.rules),
                        observed_quality(self.io.cp['client_hex'], self.rules))
        self.assertEqual(len(row['prefix_recoveries']), len(row['input_route']))
        for index, recovery in enumerate(row['prefix_recoveries'], 1):
            endpoint = replay_native_route(self.io.cp['pose'], row['input_route'][:index],
                self.io.geometry, self.io.settings, wheel_delta_per_step=1.,
                sample_policy='all_recorded_points')['final_pose']
            checked = audit_candidate_endpoint(context, self.checkpoint_at(endpoint),
                                               self.rules, recovery)
            self.assertLessEqual(predicted_quality(checked['prediction'], self.rules),
                                 observed_quality(self.io.cp['client_hex'], self.rules))
            self.assertTrue(recovery['neighborhood_audit']['all_samples_baseline_or_better'])
            self.assertGreaterEqual(recovery['neighborhood_audit']['samples'], 81)

    def test_expired_search_has_no_publishable_trial(self):
        m = self.module()
        self.assertIsNone(m.find_refinement(self.context(), self.io.cp, self.rules,
            deadline=1., clock=lambda: 1.))

    def test_expired_recovery_does_not_call_an_io_check_that_raises_local_timeout(self):
        m = self.module()
        def io_check():
            raise TimeoutError('Local planning deadline expired')
        try:
            row = m.find_recovery(self.context(), self.io.cp, self.io.cp,
                self.rules, deadline=1., clock=lambda: 1., check=io_check)
        except TimeoutError:
            self.fail('Expired local recovery must return None without calling expired IO')
        self.assertIsNone(row)

    def test_io_timeout_after_crossing_local_recovery_deadline_returns_no_candidate(self):
        m = self.module()
        tick = [0.]
        def io_check():
            tick[0] = 1.
            raise TimeoutError('Local planning deadline expired during read')
        try:
            row = m.find_recovery(self.context(), self.io.cp, self.io.cp,
                self.rules, deadline=1., clock=lambda: tick[0], check=io_check)
        except TimeoutError:
            self.fail('A read crossing local recovery expiry must return None')
        self.assertIsNone(row)

    def test_recovery_preserves_an_io_timeout_before_local_deadline(self):
        m = self.module()
        def io_check():
            raise TimeoutError('Unrelated input or process deadline')
        with self.assertRaisesRegex(TimeoutError, 'Unrelated'):
            m.find_recovery(self.context(), self.io.cp, self.io.cp, self.rules,
                deadline=2., clock=lambda: 1., check=io_check)

    def test_interrupt_is_propagated_before_a_proposal_is_retained(self):
        m = self.module()
        def cancelled():
            raise InterruptedError('F9')
        with self.assertRaises(InterruptedError):
            m.find_refinement(self.context(), self.io.cp, self.rules,
                deadline=100., clock=lambda: 1., check=cancelled)

    def test_deadline_during_return_audit_cannot_publish_a_partial_proof(self):
        m = self.module()
        tick = [0.]
        def check():
            tick[0] += .01
        row = m.find_refinement(self.context(), self.io.cp, self.rules,
            deadline=.35, clock=lambda: tick[0], check=check, radius_pixels=1)
        self.assertIsNone(row)

    def test_current_accepted_exact_target_needs_no_trial(self):
        m = self.module()
        rules = [dict(enabled=True, exact=True, colors=[c], tolerance=0.)
                 for c in self.io.cp['client_hex']]
        self.assertIsNone(m.find_refinement(self.context(), self.io.cp, rules,
            deadline=time.monotonic()+1.))

    def test_recovery_replays_from_measured_state_and_corrects_extra_pixel(self):
        m = self.module()
        c = self.io
        trial = native_drag_gesture(c.geometry, c.settings, -1, 0).record()
        endpoint = replay_native_route(c.cp['pose'], [trial], c.geometry, c.settings,
            wheel_delta_per_step=1., sample_policy='all_recorded_points')['final_pose']
        disturbed = copy.deepcopy(endpoint)
        disturbed['position'][0] += 2./(c.geometry.board[2]-c.geometry.board[0])
        measured = self.checkpoint_at(disturbed)
        self.assertGreater(observed_quality(measured['client_hex'], self.rules),
                           observed_quality(c.cp['client_hex'], self.rules))
        preferred = [native_drag_gesture(c.geometry, c.settings, 1, 0).record()]
        row = m.find_recovery(self.context(), measured, c.cp, self.rules,
            deadline=time.monotonic()+2., preferred_routes=(preferred,))
        self.assertIsNotNone(row)
        self.assertTrue(row['input_route'])
        checked = audit_candidate_endpoint(self.context(), measured, self.rules, row)
        self.assertLessEqual(predicted_quality(checked['prediction'], self.rules),
                             observed_quality(c.cp['client_hex'], self.rules))

    def test_already_better_measured_endpoint_needs_no_return_input(self):
        m = self.module()
        c = self.io
        route = [native_drag_gesture(c.geometry, c.settings, -3, 0).record()]
        pose = replay_native_route(c.cp['pose'], route, c.geometry, c.settings,
            wheel_delta_per_step=1., sample_policy='all_recorded_points')['final_pose']
        row = m.find_recovery(self.context(), self.checkpoint_at(pose), c.cp, self.rules,
            deadline=time.monotonic()+1.)
        self.assertIsNotNone(row)
        self.assertEqual(row['input_route'], [])
        self.assertTrue(row['endpoint_audit']['full_route_replayed'])


class RecordedRc11RefinementTests(unittest.TestCase):
    module = ProtectedRefinementTests.module
    context = ProtectedRefinementTests.context
    checkpoint_at = ProtectedRefinementTests.checkpoint_at
    def setUp(self):
        folder = Path(__file__).parent/'fixtures/native_live/rc11_refinement'
        case = json.loads(read_local_fixture_text(folder/'case.json', encoding='utf-8'))
        cp = copy.deepcopy(case['initial'])
        self.io = type('RecordedFixture', (), {})()
        self.io.cp = cp
        self.io.session = load_local_palette_session(folder/'palette')
        self.io.settings = InputSettings(**case['settings'])
        self.io.geometry = InputGeometry(cp['board'], cp['local_size'], 'windows_legacy_mouse_pixels')
        self.rules = case['rules']

    def test_measured_extra_pixel_at_first_prefix_is_corrected_before_inverse_rotation(self):
        m = self.module()
        row = m.find_refinement(self.context(), self.io.cp, self.rules,
            deadline=time.monotonic()+3.)
        self.assertIsNotNone(row)
        drag = native_drag_gesture(self.io.geometry, self.io.settings, 1, 1).record()
        pose = replay_native_route(self.io.cp['pose'], [row['input_route'][0], drag],
            self.io.geometry, self.io.settings, wheel_delta_per_step=1.,
            sample_policy='all_recorded_points')['final_pose']
        actual = self.checkpoint_at(pose)
        recovery = m.find_recovery(self.context(), actual, self.io.cp, self.rules,
            deadline=time.monotonic()+2., preferred_routes=(row['prefix_recoveries'][0]['input_route'],))
        self.assertIsNotNone(recovery)
        checked = audit_candidate_endpoint(self.context(), actual, self.rules, recovery)
        self.assertLessEqual(predicted_quality(checked['prediction'], self.rules),
                             observed_quality(self.io.cp['client_hex'], self.rules))

    def test_saved_rc11_improves_with_two_rotations_and_no_wheel_inverse_assumption(self):
        m = self.module()
        start = time.monotonic()
        row = m.find_refinement(self.context(), self.io.cp, self.rules,
            deadline=start+3.)
        self.assertIsNotNone(row)
        self.assertLess(time.monotonic()-start, 3.1)
        self.assertLess(row['refinement_metrics']['maximum'], 1.)
        self.assertEqual([g['kind'] for g in row['input_route']], ['rotate', 'rotate'])
        self.assertFalse(row['prediction']['predicted_accepted'])
        self.assertFalse(row['prediction']['target_exact'])
        self.assertEqual(len(row['prefix_recoveries']), 2)
        for recovery in row['prefix_recoveries']:
            self.assertLessEqual(recovery['recovery_quality'], row['baseline_quality'])
            self.assertTrue(recovery['neighborhood_audit']['all_samples_baseline_or_better'])

    def test_improving_trial_has_an_audited_return_for_every_prefix(self):
        # The recorded basin has no beneficial nonzero integer drag.
        self.test_saved_rc11_improves_with_two_rotations_and_no_wheel_inverse_assumption()

    def test_excluded_routes_are_not_returned_again(self):
        m = self.module()
        row = m.find_refinement(self.context(), self.io.cp, self.rules,
            deadline=time.monotonic()+3.)
        self.assertIsNotNone(row)
        other = m.find_refinement(self.context(), self.io.cp, self.rules,
            deadline=time.monotonic()+3., excluded=(row['input_route'],))
        if other is not None:
            self.assertNotEqual(other['input_route'], row['input_route'])


class RecordedRc12RefinementTests(unittest.TestCase):
    module = ProtectedRefinementTests.module
    context = ProtectedRefinementTests.context
    checkpoint_at = ProtectedRefinementTests.checkpoint_at

    def fixture(self, name):
        folder = Path(__file__).parent/'fixtures/native_live'/name
        case = json.loads(read_local_fixture_text(folder/'case.json', encoding='utf-8'))
        self.io = type('RecordedFixture', (), {})()
        self.io.cp = copy.deepcopy(case['initial'])
        self.io.session = load_local_palette_session(folder/'palette')
        self.io.settings = InputSettings(**case['settings'])
        self.io.geometry = InputGeometry(self.io.cp['board'], self.io.cp['local_size'],
                                         'windows_legacy_mouse_pixels')
        self.rules = case['rules']

    def test_triple_exact_basin_is_found_with_finer_angle_and_pivot_routes(self):
        self.fixture('rc12_refinement_triple')
        m = self.module()
        row = m.find_refinement(self.context(), self.io.cp, self.rules,
            deadline=time.monotonic()+3.)
        self.assertIsNotNone(row, 'The recorded triple basin has an audited exact route')
        self.assertTrue(row['prediction']['predicted_accepted'])
        self.assertEqual(row['prediction']['colors'], ['#000000']*3)
        for recovery in row['prefix_recoveries']:
            self.assertTrue(recovery['neighborhood_audit']['all_samples_baseline_or_better'])

    def test_double_exact_basin_is_found_beyond_old_candidate_cutoff(self):
        self.fixture('rc12_refinement_double')
        m = self.module()
        row = m.find_refinement(self.context(), self.io.cp, self.rules,
            deadline=time.monotonic()+10.)
        self.assertIsNotNone(row)
        self.assertTrue(row['prediction']['predicted_accepted'])
        self.assertEqual(row['prediction']['colors'][:2], ['#000000']*2)
        self.assertIsNone(row['prediction']['colors'][2])

    def test_diagnostics_distinguish_deadline_from_finite_family_exhaustion(self):
        self.fixture('rc12_refinement_triple')
        m = self.module()
        if 'stats' not in __import__('inspect').signature(m.find_refinement).parameters:
            self.fail('Local search must report deadline and finite family evidence')
        stats = {}
        self.assertIsNone(m.find_refinement(self.context(), self.io.cp, self.rules,
            deadline=1., clock=lambda: 1., stats=stats))
        self.assertTrue(stats['deadline_reached'])
        self.assertFalse(stats['family_exhausted'])
        self.assertEqual(stats['checked_routes'], 0)
        json.dumps(stats, allow_nan=False)

    def test_search_progress_reports_json_serializable_observed_work(self):
        self.fixture('rc12_refinement_triple')
        m = self.module()
        parameters = __import__('inspect').signature(m.find_refinement).parameters
        if 'stats' not in parameters or 'progress' not in parameters:
            self.fail('Local search must expose stage progress and search evidence')
        stats = {}
        updates = []
        row = m.find_refinement(self.context(), self.io.cp, self.rules,
            deadline=time.monotonic()+3., stats=stats, progress=updates.append)
        self.assertIsNotNone(row)
        self.assertGreater(stats['checked_routes'], 0)
        self.assertGreater(stats['return_checked'], 0)
        self.assertTrue(stats['protected_candidate_found'])
        self.assertFalse(stats['deadline_reached'])
        self.assertTrue(updates)
        self.assertTrue(any(update['stage'].endswith('rotation_pairs') for update in updates))
        json.dumps(updates, allow_nan=False)


if __name__ == '__main__':
    unittest.main()
