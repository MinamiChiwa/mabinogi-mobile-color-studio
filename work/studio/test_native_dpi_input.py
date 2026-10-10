"""Physical pixel staircases must reach the same exact native replay kernel.

The complete integer tables below are synthetic offline coordinate fixtures,
not claims of live HWND authentication or DPI rounding measurements.
"""
import copy
import math
import unittest

import numpy as np

from native_input_response import InputGeometry, InputSettings, replay_native_route
from native_input_compile import native_drag_gesture
from native_input_pipeline import bind_native_route_seeds, search_native_input_pipeline
from native_palette_search import PoseGrid
from native_live.same_session_dye_planner import bind_planning_context, audit_candidate_endpoint
from native_live import refinement
from test_native_live_controller import FixtureIO


def mapping(scale=1., native_size=(1000, 900), native_board=(100., 100., 800., 800.),
            viewport_origin=(0, 0), viewport_scale=(1., 1.)):
    size = [round(v*scale) for v in native_size]
    return dict(source='offline_complete_pixel_lattice_fixture',
        physical_client_size=size, native_screen_size=list(native_size),
        target_client_size=list(native_size), native_board_top_left=list(native_board),
        target_client_x_by_physical_x=[math.floor(x/scale) for x in range(size[0])],
        target_client_y_by_physical_y=[math.floor(y/scale) for y in range(size[1])],
        viewport_origin=list(viewport_origin), viewport_scale=list(viewport_scale),
        coordinate_validation=dict(verified=True,
            scheme='physical_to_logical_for_hwnd_then_target_context_screen_to_client',
            fixture_only=True))


def geometry(scale=1., **kwargs):
    packet = mapping(scale, **kwargs)
    board = tuple(v*scale for v in packet['native_board_top_left'])
    return InputGeometry(board, (700., 700.), 'windows_legacy_mouse_pixels',
                         pixel_mapping=packet)


class NativeDpiInputTests(unittest.TestCase):
    def test_explicit_dpi_mapping_is_part_of_geometry(self):
        self.assertIn('pixel_mapping', InputGeometry.__dataclass_fields__,
                      'InputGeometry cannot represent the physical input staircase')

    def test_physical_pixels_use_target_tables_at_125_150_175_and_200_percent(self):
        # These two adjacent physical samples straddle/collide on the supplied
        # integer target lattice. A smooth physical board affine cannot agree.
        for scale, points, expected in (
                (1.25, ([562, 562], [563, 563]), ([-1., 0.], [0., -1.])),
                (1.50, ([675, 675], [676, 676]), ([0., -1.], [0., -1.])),
                (1.75, ([787, 787], [788, 788]), ([-1., 0.], [0., -1.])),
                (2.00, ([900, 900], [901, 901]), ([0., -1.], [0., -1.]))):
            with self.subTest(scale=scale):
                g = geometry(scale)
                for point, want in zip(points, expected):
                    np.testing.assert_array_equal(g.local(point), want)

    def test_mapped_one_to_one_replay_is_bitwise_identical_to_legacy(self):
        old = InputGeometry((100., 100., 800., 800.), (700., 700.),
                            'windows_legacy_mouse_pixels')
        new = geometry()
        settings = InputSettings(.5, 3., 5., .1, .01)
        reference = dict(position=[.123, -.25], scale=1.1, rotation_degrees=2.3)
        route = [native_drag_gesture(old, settings, 3, -2).record(),
                 dict(kind='rotate', right=True, points=[[450, 450], [620, 450], [620, 451]]),
                 dict(kind='wheel', points=[[460, 430]], wheel_steps=-1)]
        a = replay_native_route(reference, route, old, settings,
            sample_policy='all_recorded_points', wheel_delta_per_step=1.)
        b = replay_native_route(reference, route, new, settings,
            sample_policy='all_recorded_points', wheel_delta_per_step=1.)
        self.assertEqual(a['final_pose'], b['final_pose'])
        self.assertEqual(a['trace'], b['trace'])

    def test_native_viewport_floor_runs_after_target_coordinate_table(self):
        g = geometry(viewport_origin=(3, 4), viewport_scale=(.8, 1.25))
        # float32((450-3)*.8)=357.6 -> 357; (450-4)*1.25=557.5 -> 557.
        np.testing.assert_array_equal(g.local([450, 450]), [-93., -108.])

    def test_viewport_subtraction_casts_each_integer_to_float32_first(self):
        packet = mapping(viewport_origin=(16777217, 0))
        g = InputGeometry((100., 100., 800., 800.), (7., 7.),
                          'windows_legacy_mouse_pixels', pixel_mapping=packet)
        # float32(16777217)=16777216; float32(450)-that = -16776766.
        # Native board affine then yields float32(-167772.16).
        self.assertEqual(float(g.local([450, 450])[0]), -167772.15625)

    def test_missing_proof_and_noninteger_physical_points_are_rejected(self):
        packet = mapping(1.5)
        packet.pop('coordinate_validation')
        with self.assertRaises(ValueError):
            InputGeometry((150., 150., 1200., 1200.), (700., 700.),
                          'windows_legacy_mouse_pixels', pixel_mapping=packet)
        g = geometry(1.5)
        for point in ([450.25, 450], [450.000001, 450], [-1, 450], [1500, 450]):
            with self.assertRaises(ValueError):
                g.local(point)
        with self.assertRaises(ValueError):
            replay_native_route(dict(position=[0., 0.], scale=1., rotation_degrees=0.),
                [dict(kind='wheel', points=[[450.000001, 450]], wheel_steps=1)],
                g, InputSettings(.5, 3., 5., .1, .01),
                sample_policy='all_recorded_points', wheel_delta_per_step=1.)

    def test_inverse_pivot_selects_nearest_reachable_native_pixel(self):
        g = geometry(1.5)
        point = g.normalized_to_physical([.5, .5])
        np.testing.assert_array_equal(g.normalized(g.local(point)), [.5, .5])
        self.assertEqual(tuple(point), (675, 674))

    def test_micro_drag_threshold_uses_native_lattice(self):
        g = geometry(2.)
        settings = InputSettings(.5, 3., 5., .1, .01)
        gesture = native_drag_gesture(g, settings, 1, 0)
        result = replay_native_route(dict(position=[0., 0.], scale=1., rotation_degrees=0.),
            [gesture.record()], g, settings, sample_policy='all_recorded_points')
        self.assertGreater(result['diagnostics']['accepted_moves'], 0)
        self.assertEqual(result['final_pose']['position'], [0., 0.])

    def test_micro_drag_kick_crosses_a_nonunit_viewport_floor_plateau(self):
        packet = mapping(native_board=(10., 10., 80., 80.), viewport_scale=(.1, .1))
        g = InputGeometry((100., 100., 800., 800.), (700., 700.),
                          'windows_legacy_mouse_pixels', pixel_mapping=packet)
        settings = InputSettings(.5, 3., 5., .1, .01)
        gesture = native_drag_gesture(g, settings, 1, 0)
        result = replay_native_route(dict(position=[0., 0.], scale=1., rotation_degrees=0.),
            [gesture.record()], g, settings, sample_policy='all_recorded_points')
        self.assertGreater(result['diagnostics']['accepted_moves'], 0)
        self.assertEqual(result['final_pose']['position'], [0., 0.])

    def test_mapping_change_invalidates_route_seed_binding(self):
        io = FixtureIO()
        board = io.geometry.board
        packet = mapping(1., native_size=(1600, 1200), native_board=board)
        g = InputGeometry(board, io.geometry.local_size, 'windows_legacy_mouse_pixels',
                          pixel_mapping=packet)
        bundle = bind_native_route_seeds(io.session, g, io.settings, [[]],
            wheel_delta_per_step=1., sample_policy='all_recorded_points')
        changed = copy.deepcopy(packet)
        changed['target_client_x_by_physical_x'][100] = 99
        other = InputGeometry(board, io.geometry.local_size, 'windows_legacy_mouse_pixels',
                              pixel_mapping=changed)
        with self.assertRaises(ValueError):
            search_native_input_pipeline(io.session, PoseGrid((0., 0.), (0., 0.), 1, 1, (1.,), (0.,)),
                other, io.settings, io.case['rules'], seed_bundle=bundle,
                wheel_delta_per_step=1., sample_policy='all_recorded_points', now=0., deadline=120.)

    def test_context_retains_mapping_and_detects_pixel_lattice_mutation(self):
        io = FixtureIO()
        packet = mapping(1., native_size=(1600, 1200), native_board=io.geometry.board)
        cp = copy.deepcopy(io.cp)
        cp['pixel_mapping'] = packet
        g = InputGeometry(cp['board'], cp['local_size'], 'windows_legacy_mouse_pixels',
                          pixel_mapping=packet)
        context = bind_planning_context(io.session, cp, g, io.settings,
            wheel_delta_per_step=1., calibration_evidence=dict(source='offline_test',
            viewport_origin=[0, 0], viewport_scale=[1, 1],
            backend_during_actions_synchronously_recorded=True))
        self.assertEqual(refinement._geometry(context)[0].local([1000, 600]).tolist(),
                         g.local([1000, 600]).tolist())
        self.assertIsNotNone(context.get('pixel_mapping'), 'Planning dropped the measured pixel lattice')
        context['pixel_mapping']['target_client_x_by_physical_x'][100] = 99
        with self.assertRaises(ValueError):
            audit_candidate_endpoint(context, cp, io.case['rules'], {})

    def test_cached_refinement_events_equal_full_replay_with_staircase(self):
        io = FixtureIO()
        scale = 1.5
        packet = mapping(scale, native_size=(1600, 1200), native_board=io.geometry.board)
        context = dict(board=[v*scale for v in io.geometry.board],
            local_size=list(io.geometry.local_size), input_coordinate_convention='windows_legacy_mouse_pixels',
            pixel_mapping=packet, settings=vars(io.settings), wheel_delta_per_step=1.)
        g, settings = refinement._geometry(context)
        self.assertIsNotNone(g.pixel_mapping, 'Refinement dropped the measured pixel lattice')
        count = 0
        for stage, route, endpoint in refinement._local_proposals(context, io.cp['pose'], 1, lambda: None):
            if stage == 'integer_drags':
                continue
            expected = replay_native_route(io.cp['pose'], route, g, settings,
                sample_policy='all_recorded_points', wheel_delta_per_step=1.)['final_pose']
            self.assertEqual(endpoint, expected)
            count += 1
            if count == 20:
                break
        self.assertEqual(count, 20)

    def test_175_percent_plateau_keeps_native_rotation_family_available(self):
        io = FixtureIO()
        scale = 1.75
        packet = mapping(scale, native_size=(1600, 1200), native_board=io.geometry.board)
        context = dict(board=[v*scale for v in io.geometry.board],
            local_size=list(io.geometry.local_size), input_coordinate_convention='windows_legacy_mouse_pixels',
            pixel_mapping=packet, settings=vars(io.settings), wheel_delta_per_step=1.)
        g, settings = refinement._geometry(context)
        # The fixture center is on a physical y plateau: +1 physical pixel
        # maps to the same q, but +2 reaches the next native pixel.
        l, t, r, b = g.board
        anchor = (round((l+r)/2), round((t+b)/2))
        self.assertEqual(g.local(anchor).tolist(), g.local((anchor[0], anchor[1]+1)).tolist())
        count = 0
        for stage, route, endpoint in refinement._local_proposals(context, io.cp['pose'], 1, lambda: None):
            if stage == 'integer_drags':
                continue
            replay = replay_native_route(io.cp['pose'], route, g, settings,
                sample_policy='all_recorded_points', wheel_delta_per_step=1.)
            self.assertEqual(endpoint, replay['final_pose'])
            self.assertGreater(replay['diagnostics']['accepted_rotations'], 0)
            count += 1
            if count == 5:
                break
        self.assertEqual(count, 5, 'Native rotation family vanished on the physical pixel plateau')


if __name__ == '__main__':
    unittest.main()
