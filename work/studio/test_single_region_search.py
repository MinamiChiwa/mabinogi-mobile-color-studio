"""Independent live-feedback tests; never import Windows/game input APIs."""
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from single_region_search import (QuickSearchLimits, global_motion,
                                  run_single_region, visible_candidates)


def rules(color='#FFFFFF', *, exact=False, region=0, tolerance=8):
    return [dict(enabled=i == region, colors=[color], exact=exact,
                 tolerance=0 if exact else tolerance) for i in range(3)]


def scene(size=300, origin=(0, 0)):
    l, t = origin
    return SimpleNamespace(board=(l, t, l+size, t+size),
                           markers=[(l+size/6, t+size/2),
                                    (l+size/2, t+size/2),
                                    (l+5*size/6, t+size/2)], cards=[])


class UserStopped(Exception):
    pass


class FakeIO:
    """Integer commands drive an independent translation and pixel sampler."""
    def __init__(self, base=None, *, gain=1., color=None, measured=True):
        self.base = np.full((300, 300, 3), 80, np.uint8) if base is None else base
        self.gain = gain
        self.color = color
        self.measured = measured
        self.offset = np.zeros(2, float)
        self.now = 0.
        self.commands = []
        self.reads = []
        self.events = []
        self.frames = {}
        self.stopped = False
        self.capture_calls = 0

    def clock(self):
        return self.now

    def check(self):
        if self.stopped:
            raise UserStopped('F9')

    def capture(self):
        self.check()
        self.capture_calls += 1
        self.now += .01
        image = cv2.warpAffine(self.base, np.column_stack((np.eye(2), self.offset)),
                               (self.base.shape[1], self.base.shape[0]),
                               flags=cv2.INTER_NEAREST, borderMode=cv2.BORDER_WRAP)
        self.frames[id(image)] = self.offset.copy()
        return image

    def drag(self, board, dx, dy):
        self.check()
        self.commands.append((dx, dy))
        self.offset += np.asarray([dx, dy]) * self.gain
        self.now += .2

    def read(self, image, *, enabled, deadline):
        self.check()
        self.reads.append((tuple(enabled), deadline))
        self.now += .05
        if callable(self.color):
            value = self.color(self.offset)
        else:
            value = self.color
        output = []
        for index, active in enumerate(enabled):
            if not active:
                output.append(None)
                continue
            x, y = round((index+.5)*self.base.shape[1]/3), self.base.shape[0]//2
            output.append(value if value is not None else '#%02X%02X%02X' % tuple(image[y, x]))
        return output

    def measure(self, before, after, found_scene):
        self.check()
        self.now += .02
        if not self.measured:
            return None
        displacement = self.frames[id(after)] - self.frames[id(before)]
        return dict(matrix=np.column_stack((np.eye(2), displacement)).tolist(), origin=[0, 0])

    def pause(self, seconds):
        self.check()
        self.now += seconds

    def emit(self, kind, **data):
        self.events.append((kind, data))


class VisibleCandidateTests(unittest.TestCase):
    def test_exact_native_pixel_survives_neighborhood_risk(self):
        image = np.full((300, 300, 3), 180, np.uint8)
        image[181, 79] = 0
        rows = visible_candidates(image, scene(), rules('#000000', exact=True))
        self.assertTrue(rows[0]['screenshot_exact'])
        np.testing.assert_array_equal(rows[0]['source'], [79, 181])
        self.assertEqual(rows[0]['center_delta'], 0)
        self.assertGreater(rows[0]['worst_delta'], 60)
        self.assertFalse(rows[0]['predicted_accepted'])

    def test_same_mean_but_small_black_pixel_is_not_stable_white(self):
        image = np.full((300, 300, 3), 80, np.uint8)
        image[80:83, 77:80] = 255
        image[81, 78] = 0
        image[180:189, 77:86] = 250
        rows = visible_candidates(image, scene(), rules(tolerance=4))
        self.assertLess(rows[0]['worst_delta'], 4)
        self.assertGreater(rows[0]['source'][1], 170)

    def test_similar_black_keeps_native_center_seed_beside_stable_compromise(self):
        image = np.full((300, 300, 3), 80, np.uint8)
        image[180, 80] = 0
        image[80:89, 75:84] = 20
        rows = visible_candidates(image, scene(), rules('#000000', tolerance=8))
        self.assertGreater(rows[0]['center_delta'], 0)
        self.assertTrue(any(row['center_delta'] == 0 for row in rows))
        native = next(row for row in rows if row['center_delta'] == 0)
        self.assertGreater(native['worst_delta'], 0)
        self.assertFalse(native['predicted_accepted'])

    def test_complete_marker_column_is_excluded_at_every_height(self):
        image = np.full((300, 300, 3), 80, np.uint8)
        # Marker spacing is 100 rather than the 166 reference: the shared
        # corridor scales to 11 physical pixels on either side.
        image[:, 39:62] = 255
        rows = visible_candidates(image, scene(), rules(exact=True))
        self.assertFalse(any(row['screenshot_exact'] for row in rows))
        self.assertTrue(all(abs(row['source'][0]-50) > 11 for row in rows))

    def test_dark_linear_rendering_is_a_candidate_but_not_game_hex(self):
        image = np.full((300, 300, 3), 80, np.uint8)
        image[180:190, 75:85] = (13, 13, 0)
        rows = visible_candidates(image, scene(), rules('#080803', exact=True))
        self.assertTrue(rows[0]['screenshot_exact'])
        self.assertEqual(rows[0]['color'], '#0D0D00')
        io = FakeIO(image, color='#0D0D00')
        result = run_single_region(io, scene(), rules('#080803', exact=True),
                                   game_deadline=100,
                                   limits=QuickSearchLimits(max_candidate_trials=1, max_explorations=0))
        self.assertFalse(result['accepted'])
        self.assertTrue(result['verified'])

    def test_material_and_origin_follow_each_enabled_region(self):
        for region in range(3):
            for size in (150, 300, 600):
                with self.subTest(region=region, size=size):
                    found = scene(size, origin=(20, 30))
                    image = np.full((size+30, size+20, 3), 80, np.uint8)
                    x = round(20+(region+.8)*size/3)
                    y = 30+round(size*.7)
                    image[y-2:y+3, x-2:x+3] = 255
                    rows = visible_candidates(image, found, rules(exact=True, region=region))
                    self.assertTrue(rows[0]['screenshot_exact'])
                    self.assertEqual(rows[0]['region'], region)

    def test_invalid_activation_or_geometry_is_rejected(self):
        with self.assertRaises(ValueError):
            visible_candidates(np.zeros((300, 300, 3), np.uint8), scene(),
                               [dict(enabled=True)]*3)
        with self.assertRaises(ValueError):
            visible_candidates(np.zeros((10, 10, 3), np.uint8), scene(), rules())


class LiveSearchTests(unittest.TestCase):
    def test_no_stable_entry_read_sends_no_exploration_input(self):
        io=FakeIO();io.read=lambda *a,**k:[None]*3
        with patch('single_region_search.visible_candidates') as scan:
            result=run_single_region(io,scene(),rules('#FFFFFF',exact=True),game_deadline=100)
        self.assertFalse(result['verified']);self.assertEqual(io.commands,[])
        self.assertEqual(result['reason'],'baseline_unverified');scan.assert_not_called()

    def test_exact_miss_restores_entry_near_white_and_keeps_baseline_separate(self):
        io=FakeIO(color=lambda offset:'#FFFEFE' if not offset.any() else '#777777')
        with patch('single_region_search.visible_candidates',
                   return_value=[dict(source=np.array([85.,180.]))]):
            result=run_single_region(io,scene(),rules('#FFFFFF',exact=True),game_deadline=100,
                limits=QuickSearchLimits(max_candidate_trials=1,max_explorations=0))
        self.assertEqual(result['actual_colors'][0],'#FFFEFE')
        self.assertTrue(result['best_current']);self.assertTrue(result['compromise'])
        self.assertEqual(result['baseline_result']['actual_colors'][0],'#FFFEFE')
        self.assertEqual(result['best_observed_result']['actual_colors'][0],'#FFFEFE')

    def test_library_finish_reserve_remains_overridable(self):
        self.assertEqual(QuickSearchLimits().finish_reserve_seconds, 1.)
        self.assertEqual(QuickSearchLimits(finish_reserve_seconds=15.).finish_reserve_seconds, 15.)

    def test_initial_similarity_hit_is_double_verified_and_never_moves(self):
        io = FakeIO(color='#FEFEFE')
        result = run_single_region(io, scene(), rules(tolerance=4), game_deadline=100)
        self.assertTrue(result['accepted'])
        self.assertEqual(result['outcome'], 'matched')
        self.assertTrue(result['verified'])
        self.assertTrue(result['best_current'])
        self.assertEqual(result['reason'], 'matched')
        self.assertEqual(len(io.reads), 2)
        self.assertEqual(io.commands, [])
        self.assertTrue(all(enabled == (True, False, False) for enabled, _ in io.reads))

    def test_initial_exact_hit_is_double_verified_and_never_moves(self):
        io = FakeIO(color='#080803')
        result = run_single_region(io, scene(), rules('#080803', exact=True), game_deadline=100)
        self.assertTrue(result['accepted'])
        self.assertEqual(io.commands, [])

    def test_single_transient_exact_read_is_not_reported_as_match(self):
        io = FakeIO(color='#888888')
        reads = ['#FFFFFF', '#888888', '#888888']
        io.color = lambda _offset: reads.pop(0) if reads else '#888888'
        with patch('single_region_search.visible_candidates', return_value=[]):
            result = run_single_region(io, scene(), rules(exact=True), game_deadline=100,
                                       limits=QuickSearchLimits(max_explorations=0))
        self.assertFalse(result['accepted'])
        self.assertTrue(result['verified'])
        self.assertEqual(result['actual_colors'][0], '#888888')
        self.assertEqual(len(io.reads), 3)

    def test_exact_miss_keeps_searching_and_returns_measured_compromise(self):
        """An exact target miss is a usable near-colour outcome, not a stop."""
        io = FakeIO(color='#888888')
        with patch('single_region_search.visible_candidates', return_value=[]):
            result = run_single_region(
                io, scene(), rules('#FFFFFF', exact=True), game_deadline=100,
                limits=QuickSearchLimits(max_explorations=2, max_zoom_levels=0))
        # The search still spends its bounded exploration allowance instead
        # of treating the absent #FFFFFF sample as an unrecoverable failure.
        self.assertEqual(result['explorations'], 2)
        self.assertTrue(result['verified'])
        self.assertFalse(result['accepted'])
        self.assertTrue(result['compromise'])
        self.assertTrue(result['exact_target_missed'])
        self.assertEqual(result['outcome'], 'compromise')
        self.assertTrue(result['best_current'])
        self.assertEqual(result['actual_colors'][0], '#888888')
        self.assertEqual(result['best_actual_colors'][0], '#888888')

    def test_measured_target_hit_finishes_without_followup_exploration(self):
        image = np.full((300, 300, 3), 80, np.uint8)
        image[175:196, 75:96] = 255
        io = FakeIO(image)
        result = run_single_region(io, scene(), rules(exact=True), game_deadline=100)
        self.assertTrue(result['accepted'])
        self.assertTrue(result['current'])
        self.assertEqual(result['moves'], 1)
        self.assertEqual(result['explorations'], 0)
        self.assertEqual(len(io.commands), 1)

    def test_residual_uses_measured_source_not_repeated_command(self):
        io = FakeIO(gain=.5, color=lambda offset: '#888888' if np.linalg.norm(offset) < .8 else '#777777')
        row = dict(source=np.array([85., 180.]))
        with patch('single_region_search.visible_candidates', return_value=[row]):
            run_single_region(io, scene(), rules(exact=True), game_deadline=100,
                              limits=QuickSearchLimits(max_candidate_trials=1, max_explorations=0))
        self.assertEqual(io.commands[0], (-35, -30))
        self.assertEqual(io.commands[1], (-18, -15))
        self.assertTrue(all(max(abs(x), abs(y)) <= 54 for x, y in io.commands))

    def test_unknown_pose_discards_target_and_searches_current_frame(self):
        io = FakeIO(measured=False, color=lambda offset: '#888888' if not offset.any() else '#777777')
        row = dict(source=np.array([85., 180.]))
        with patch('single_region_search.visible_candidates', side_effect=[[row], []]) as scan:
            result = run_single_region(io, scene(), rules(exact=True), game_deadline=100,
                                       limits=QuickSearchLimits(max_candidate_trials=1, max_explorations=0))
        self.assertEqual(scan.call_count, 2)
        self.assertEqual(len(io.commands), 1)
        self.assertFalse(result['restored'])
        self.assertFalse(result['best_current'])
        self.assertEqual(result['best_actual_colors'][0], '#888888')
        self.assertEqual(result['actual_colors'][0], '#777777')

    def test_return_reserve_prevents_leaving_verified_best(self):
        io = FakeIO(color='#888888')
        with patch('single_region_search.visible_candidates', return_value=[dict(source=np.array([85., 180.]))]):
            result = run_single_region(io, scene(), rules(), game_deadline=5.)
        self.assertEqual(io.commands, [])
        self.assertEqual(result['reason'], 'return_budget')
        self.assertTrue(result['best_current'])
        self.assertTrue(result['verified'])

    def test_worse_candidate_returns_to_measured_best(self):
        io = FakeIO(color=lambda offset: '#888888' if not offset.any() else '#777777')
        with patch('single_region_search.visible_candidates', return_value=[dict(source=np.array([85., 180.]))]):
            result = run_single_region(io, scene(), rules(), game_deadline=100,
                                       limits=QuickSearchLimits(max_candidate_trials=1, max_explorations=0))
        self.assertEqual(io.commands, [(-35, -30), (35, 30)])
        self.assertTrue(result['restored'])
        self.assertTrue(result['best_current'])
        self.assertEqual(result['actual_colors'][0], '#888888')
        self.assertFalse(result['accepted'])

    def test_geometric_return_with_different_hex_is_not_restored(self):
        io = FakeIO(color='#888888')
        def color(_offset):
            return '#888888' if not io.commands else '#777777'
        io.color = color
        with patch('single_region_search.visible_candidates', return_value=[dict(source=np.array([85., 180.]))]):
            result = run_single_region(io, scene(), rules(), game_deadline=100,
                                       limits=QuickSearchLimits(max_candidate_trials=1, max_explorations=0))
        self.assertFalse(result['restored'])
        self.assertFalse(result['best_current'])
        self.assertEqual(result['outcome'], 'compromise')
        self.assertEqual(result['actual_colors'][0], '#777777')
        self.assertEqual(result['best_actual_colors'][0], '#888888')
        self.assertTrue(result['historical_best_unrestored'])

    def test_missing_candidates_use_finite_two_axis_translation_only(self):
        io = FakeIO(color='#888888')
        with patch('single_region_search.visible_candidates', return_value=[]):
            result = run_single_region(io, scene(), rules(), game_deadline=100,
                                       limits=QuickSearchLimits(max_explorations=2))
        self.assertEqual(result['explorations'], 2)
        self.assertEqual(io.commands[:2], [(42, 0), (0, 42)])
        self.assertTrue(all(max(abs(x), abs(y)) <= 54 for x, y in io.commands))
        self.assertEqual(result['reason'], 'exploration_complete')

    def test_exploration_diagonal_directions_do_not_repeat(self):
        io = FakeIO(color='#888888')
        with patch('single_region_search.visible_candidates', return_value=[]):
            result = run_single_region(io, scene(), rules(), game_deadline=200,
                                       limits=QuickSearchLimits(max_explorations=8))
        self.assertEqual(result['explorations'], 8)
        self.assertEqual(io.commands[4], (42, 42))
        self.assertEqual(io.commands[5], (-42, 42))
        self.assertEqual(io.commands[6], (-42, -42))
        self.assertEqual(io.commands[7], (42, -42))

    def test_uniform_unpromising_frame_uses_exploration_not_pixel_chasing(self):
        io = FakeIO()
        result = run_single_region(io, scene(), rules(), game_deadline=100,
                                   limits=QuickSearchLimits(max_explorations=2))
        self.assertEqual(result['candidate_trials'], 0)
        self.assertEqual(result['explorations'], 2)
        self.assertEqual(io.commands[:2], [(42, 0), (0, 42)])

    def test_failed_candidate_trials_allow_overlapping_view_exploration(self):
        io = FakeIO(color='#111111')
        row = dict(source=np.array([85., 180.]))
        with patch('single_region_search.visible_candidates', return_value=[row]):
            result = run_single_region(io, scene(), rules(exact=True), game_deadline=200,
                                       limits=QuickSearchLimits(max_explorations=2))
        self.assertGreaterEqual(result['explorations'], 1)
        self.assertLessEqual(result['candidate_trials'], 6)
        self.assertLessEqual(result['moves'], 26)  # 18 search + 8 restore

    def test_initial_capture_failure_returns_unknown_without_motion(self):
        io = FakeIO()
        io.capture = lambda: (_ for _ in ()).throw(OSError('capture unavailable'))
        result = run_single_region(io, scene(), rules(), game_deadline=100)
        self.assertFalse(result['current'])
        self.assertFalse(result['verified'])
        self.assertIsNone(result['best_actual_colors'])
        self.assertEqual(result['actual_colors'], [None]*3)
        self.assertEqual(result['outcome'], 'unverified')
        self.assertEqual(result['reason'], 'observation_unavailable')
        self.assertEqual(io.commands, [])

    def test_initial_capture_is_retried_read_only_before_matching(self):
        io = FakeIO(color='#FFFFFF')
        original = io.capture
        attempts = []
        def capture():
            attempts.append(1)
            if len(attempts) < 3:
                raise OSError('Transient screenshot failure')
            return original()
        io.capture = capture
        result = run_single_region(io, scene(), rules(exact=True), game_deadline=100)
        self.assertEqual(len(attempts), 4)  # 2 failed + 2 independent good frames
        self.assertTrue(result['accepted'])
        self.assertEqual(io.commands, [])
        self.assertEqual(sum(kind == 'single_capture_retry' for kind, _ in io.events), 2)

    def test_guard_during_capture_retry_propagates_without_input(self):
        io = FakeIO()
        def failed():
            io.stopped = True
            raise OSError('Capture failed concurrently with F9')
        io.capture = failed
        with self.assertRaises(UserStopped):
            run_single_region(io, scene(), rules(), game_deadline=100)
        self.assertEqual(io.commands, [])
        self.assertEqual(io.reads, [])

    def test_exact_landed_seed_gets_bounded_integer_neighbor_probe(self):
        io = FakeIO(color=lambda offset: '#000000' if np.allclose(offset, [-34, -30]) else '#111111')
        row = dict(source=np.array([85., 180.]), screenshot_exact=True)
        with patch('single_region_search.visible_candidates', return_value=[row]):
            result = run_single_region(io, scene(), rules('#000000', exact=True), game_deadline=100,
                                       limits=QuickSearchLimits(max_candidate_trials=1, max_explorations=0))
        self.assertEqual(io.commands, [(-35, -30), (1, 0)])
        self.assertTrue(result['accepted'])
        self.assertEqual(result['local_trials'], 1)

    def test_failed_exact_seed_probes_at_most_two_neighbors_then_finishes(self):
        io = FakeIO(color='#111111')
        row = dict(source=np.array([85., 180.]), screenshot_exact=True)
        with patch('single_region_search.visible_candidates', return_value=[row]):
            result = run_single_region(io, scene(), rules('#000000', exact=True), game_deadline=100,
                                       limits=QuickSearchLimits(max_candidate_trials=1, max_explorations=0))
        self.assertEqual(result['local_trials'], 2)
        self.assertFalse(result['accepted'])
        self.assertTrue(result['current'])
        self.assertLessEqual(len(io.commands), 4)  # landing + 2 trials + possible return

    def test_planner_failure_keeps_verified_current_without_motion(self):
        io = FakeIO(color='#888888')
        with patch('single_region_search.visible_candidates', side_effect=ValueError('bad screenshot')):
            result = run_single_region(io, scene(), rules(), game_deadline=100)
        self.assertTrue(result['verified'])
        self.assertTrue(result['current'])
        self.assertTrue(result['best_current'])
        self.assertEqual(result['reason'], 'observation_unavailable')
        self.assertEqual(io.commands, [])

    def test_transient_ocr_failure_is_reread_then_verified(self):
        io = FakeIO(color='#FFFFFF')
        original = io.read
        with patch.object(io, 'read', side_effect=[RuntimeError('OCR unavailable'),
                                                  ['#FFFFFF', None, None],
                                                  ['#FFFFFF', None, None]]):
            result = run_single_region(io, scene(), rules(exact=True), game_deadline=100)
        self.assertTrue(result['accepted'])
        self.assertEqual(io.commands, [])

    def test_stop_during_drag_propagates_without_read_or_return(self):
        io = FakeIO(color='#888888')
        def stop(board, dx, dy):
            io.stopped = True
            raise UserStopped('F9')
        io.drag = stop
        with patch('single_region_search.visible_candidates', return_value=[dict(source=np.array([85., 180.]))]):
            with self.assertRaises(UserStopped):
                run_single_region(io, scene(), rules(), game_deadline=100)
        self.assertEqual(len(io.reads), 2)

    def test_partial_input_failure_observes_current_without_fake_return(self):
        io = FakeIO(color=lambda offset: '#888888' if not offset.any() else '#777777')
        def failed(board, dx, dy):
            io.offset += [dx/2, dy/2]
            io.commands.append((dx, dy))
            raise RuntimeError('Input interrupted halfway')
        io.drag = failed
        with patch('single_region_search.visible_candidates', return_value=[dict(source=np.array([85., 180.]))]):
            result = run_single_region(io, scene(), rules(), game_deadline=100)
        self.assertEqual(len(io.commands), 1)
        self.assertEqual(result['reason'], 'input_unverified')
        self.assertFalse(result['restored'])
        self.assertTrue(result['current'])
        self.assertEqual(result['actual_colors'][0], '#777777')

    def test_nontranslation_pose_is_not_inverted_into_return_drag(self):
        io = FakeIO(color=lambda offset: '#888888' if not offset.any() else '#777777')
        io.measure = lambda *args: dict(matrix=[[1.05, 0, -35], [0, 1.05, -30]], origin=[0, 0])
        with patch('single_region_search.visible_candidates', return_value=[dict(source=np.array([85., 180.]))]):
            result = run_single_region(io, scene(), rules(), game_deadline=100,
                                       limits=QuickSearchLimits(max_candidate_trials=1, max_explorations=0,
                                                               max_target_steps=1))
        self.assertEqual(len(io.commands), 1)
        self.assertFalse(result['restored'])
        self.assertFalse(result['best_current'])

    def test_invalid_limits_or_multi_region_are_rejected(self):
        with self.assertRaises(ValueError):
            QuickSearchLimits(max_translation_fraction=.19)
        with self.assertRaises(ValueError):
            run_single_region(FakeIO(), scene(), [dict(enabled=True)]*3, game_deadline=100)
        with self.assertRaises(ValueError):
            run_single_region(FakeIO(), scene(), rules(), game_deadline=float('inf'))


class MotionCoordinateTests(unittest.TestCase):
    def test_board_local_matrix_is_lifted_without_origin_error(self):
        matrix = global_motion(dict(matrix=[[2, 0, 3], [0, 2, -4]]), (10, 20, 310, 320))
        np.testing.assert_array_equal((matrix @ [20, 30, 1])[:2], [33, 36])

    def test_invalid_motion_does_not_create_a_pose(self):
        for value in (None, {}, dict(matrix=[[1, 0], [0, 1]]),
                      dict(matrix=[[1, 0, 0], [0, 1, 0], [1, 0, 1]]),
                      dict(matrix=[[float('nan'), 0, 0], [0, 1, 0]])):
            with self.subTest(value=value):
                self.assertIsNone(global_motion(value, (0, 0, 300, 300)))


if __name__ == '__main__':
    unittest.main()
