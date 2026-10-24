"""Late useful routes retain their actual reads, with only one game tail."""
from test_paths import STUDIO
import importlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import copy

from native_input_response import InputGeometry, InputSettings, replay_native_route
from native_palette_scoring import score_native_pose
from native_palette_search import PoseGrid
from test_support import read_local_fixture_text, load_local_palette_session


class PlannerTailTests(unittest.TestCase):
    def setUp(self):
        self.planner = importlib.import_module('native_live.same_session_dye_planner')
        folder = STUDIO / 'fixtures/native_live/stage68'
        self.case = json.loads(read_local_fixture_text(folder / 'case.json', encoding='utf-8'))
        self.session = load_local_palette_session(folder / 'palette')
        self.cp = self.case['initial']
        geometry = InputGeometry(self.cp['board'], self.cp['local_size'], 'windows_legacy_mouse_pixels')
        self.geometry = geometry
        self.settings = InputSettings(**self.case['settings'])
        self.context = self.planner.bind_planning_context(self.session, self.cp, geometry, self.settings,
            wheel_delta_per_step=1., calibration_evidence=dict(source='saved-stage68', viewport_origin=[0, 0],
                viewport_scale=[1., 1.], backend_during_actions_synchronously_recorded=True))
        self.frames = [dict(hex=self.cp['client_hex'], remaining_seconds=20, captured_monotonic=t)
                       for t in (100., 100.1)]
        self.grid = PoseGrid((0, 0), (0, 0), 1, 1, (1.,), (0.,))

    def plan(self, **options):
        # This suite owns late admission and paid-read accounting, not another
        # global search matrix under a frozen clock. Use the recorded short
        # route as a completed compiler response; the production planner still
        # fully replays and independently scores its original descriptors.
        route = [copy.deepcopy(step['gesture']) for step in self.case['actual_steps']]
        pose = replay_native_route(self.cp['pose'],route,self.geometry,self.settings,
            wheel_delta_per_step=1.,sample_policy='all_recorded_points')['final_pose']
        assert score_native_pose(self.session,pose,self.case['rules'])['predicted_accepted']
        with patch.object(self.planner,'search_periodic_targets',return_value=dict(
                candidates=[dict(native_pose=pose)],nearest_candidates=[],enabled_regions=[0,1,2])), \
             patch.object(self.planner,'compile_periodic_approach',return_value=dict(
                input_route=route,final_pose=pose)):
            return self.planner.plan_from_checkpoint(self.context, self.cp, self.frames, self.case['rules'], self.grid,
                now=100.2, engineering_deadline=200., time_budget_seconds=6., clock=lambda: 100.2, **options)

    def test_twenty_second_remaining_window_preserves_a_real_short_exact_route(self):
        result = self.plan()
        self.assertEqual(result['reserve_seconds'], 3.)
        self.assertEqual(result['effective_deadline'], 117.)
        self.assertIsNotNone(result['candidate'], result['stop_reason'])
        candidate = result['candidate']
        self.assertLess(100.2 + candidate['needed'] + result['verification_margin_seconds'], 117.)
        replay = replay_native_route(self.cp['pose'], candidate['input_route'],
            InputGeometry(self.cp['board'], self.cp['local_size'], 'windows_legacy_mouse_pixels'),
            self.settings, wheel_delta_per_step=1., sample_policy='all_recorded_points')
        self.assertTrue(score_native_pose(self.session, replay['final_pose'], self.case['rules'])['predicted_accepted'])
        self.assertFalse(result['ready_for_input'])

    def test_larger_idle_tail_cannot_silently_override_current_policy(self):
        with self.assertRaisesRegex(ValueError, 'deadline/reserve/search'):
            self.plan(reserve_seconds=8.)

    def test_completed_reference_observation_is_not_budgeted_again(self):
        result = self.plan()
        needed = result['candidate']['needed']
        now = result['effective_deadline'] - needed - .1
        fresh = [dict(frame, remaining_seconds=None, timer_advisory=True, captured_monotonic=now + offset)
                 for frame, offset in zip(self.frames, (-.1, 0.))]
        with self.assertRaisesRegex(ValueError, 'insufficient remaining time'):
            self.planner.validate_plan_reference(self.context, result, self.cp, fresh, now=now,
                rules=self.case['rules'])
        verified = self.planner.validate_plan_reference(self.context, result, self.cp, fresh, now=now,
            rules=self.case['rules'], reference_observation_paid=True)
        self.assertTrue(verified['reference_unchanged'])
        self.assertFalse(verified['ready_for_input'])


if __name__ == '__main__':
    unittest.main()
