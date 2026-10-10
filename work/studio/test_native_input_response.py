"""Catch input gates, float32 order and false reachability guarantees."""
import importlib
import importlib.util
import json
from pathlib import Path
import unittest
import numpy as np
from input_gestures import drag_gesture, grouped_rotation_gesture, wheel_gesture
from test_support import requires_local_fixture


class NativeInputResponseTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('native_input_response'),
                             'Offline native input response model is missing')
        self.m = importlib.import_module('native_input_response')
        self.settings = self.m.InputSettings(.5, 3., 5., .1, .01)
        self.geometry = self.m.InputGeometry((100, 100, 800, 800), (700, 700))
        self.reference = dict(position=[0., 0.], scale=1., rotation_degrees=0.)

    def replay(self, route, **kwargs):
        return self.m.replay_native_route(self.reference, route, self.geometry,
                                         self.settings, sample_policy='all_recorded_points', **kwargs)

    def test_windows_mouse_pixel_convention_changes_pivot_without_changing_board(self):
        geometry=self.m.InputGeometry(self.geometry.board,self.geometry.local_size,
                                       input_coordinate_convention='windows_legacy_mouse_pixels')
        self.assertEqual(geometry.board,self.geometry.board)
        self.assertEqual(geometry.normalized(geometry.local([450,450])).tolist(),
                         self.geometry.normalized(self.geometry.local([450,451])).tolist())
        self.assertEqual(self.geometry.normalized(self.geometry.local([450,450])).tolist(),[.5,.5])

    def test_unknown_input_coordinate_convention_is_rejected(self):
        with self.assertRaises(ValueError):
            self.m.InputGeometry(self.geometry.board,self.geometry.local_size,input_coordinate_convention='guess')

    def test_mouse_pixel_convention_preserves_drag_but_changes_wheel_pivot(self):
        corrected=self.m.InputGeometry(self.geometry.board,self.geometry.local_size,
                                        input_coordinate_convention='windows_legacy_mouse_pixels')
        for kind,route in [('drag',[drag_gesture(self.geometry.board,7,0).record()]),
                           ('wheel',[wheel_gesture(self.geometry.board,1).record()])]:
            old=self.replay(route,wheel_delta_per_step=1.)
            new=self.m.replay_native_route(self.reference,route,corrected,self.settings,
                    sample_policy='all_recorded_points',wheel_delta_per_step=1.)
            if kind=='drag':self.assertEqual(old['final_pose'],new['final_pose'])
            else:
                self.assertNotEqual(old['final_pose']['position'],new['final_pose']['position'])
                self.assertEqual(new['input_coordinate_convention'],'windows_legacy_mouse_pixels')

    def test_motion_matches_frozen_original_instructions_including_scale_clamps(self):
        source=Path(__file__).parent/'fixtures/native_palette/input_response_oracle.json'
        requires_local_fixture(source)
        fixture = json.loads(source.read_text())
        for row in fixture['motion_cases']:
            pose=dict(position=row['position'],scale=row['scale'],rotation_degrees=0.)
            actual=self.m.apply_motion_event(pose,row['pivot'],row['move'],row['zoom'],row['delta'],self.settings)
            np.testing.assert_array_equal(actual['position'],row['expected_position'])
            self.assertEqual(actual['scale'],row['expected_scale'])

    def test_signed_angle_matches_independent_oracle_including_micro_angle_zero(self):
        source=Path(__file__).parent/'fixtures/native_palette/input_response_oracle.json'
        requires_local_fixture(source)
        fixture = json.loads(source.read_text())
        for row in fixture['signed_angle_cases']:
            self.assertEqual(self.m.native_signed_angle(row['a'],row['b']),row['expected'])

    def test_fresh_micro_drag_is_discarded_instead_of_translating_endpoint(self):
        result=self.replay([drag_gesture(self.geometry.board, 4, 0).record()])
        self.assertEqual(result['final_pose'],self.reference)
        self.assertEqual(result['diagnostics']['accepted_moves'],0)

    def test_threshold_accumulates_from_last_accepted_point_and_equal_is_accepted(self):
        route=[dict(kind='drag',points=[[450,450],[454,450],[455,450],[456,450]])]
        result=self.replay(route)
        self.assertEqual(result['diagnostics']['accepted_moves'],2)
        self.assertAlmostEqual(result['final_pose']['position'][0],6/700,places=7)

    def test_separate_small_drags_reset_threshold(self):
        gesture=drag_gesture(self.geometry.board,4,0).record()
        self.assertEqual(self.replay([gesture,gesture])['final_pose'],self.reference)

    def test_local_coordinate_scale_changes_acceptance_without_changing_pixel_route(self):
        geometry=self.m.InputGeometry((100,100,800,800),(1400,1400))
        gesture=drag_gesture(geometry.board,4,0).record()
        result=self.m.replay_native_route(self.reference,[gesture],geometry,self.settings,
                                         sample_policy='all_recorded_points')
        self.assertAlmostEqual(result['final_pose']['position'][0],4/700,places=7)

    def test_drag_y_is_inverted_for_native_uv(self):
        result=self.replay([drag_gesture(self.geometry.board,0,7).record()])
        self.assertAlmostEqual(result['final_pose']['position'][1],-7/700,places=7)

    def test_rotation_radial_segment_does_not_rotate_but_tangent_does(self):
        route=[dict(kind='rotate',right=True,points=[[450,450],[590,450],[590,457]])]
        result=self.replay(route)
        self.assertLess(result['final_pose']['rotation_degrees'],-2.)
        self.assertEqual(result['diagnostics']['accepted_rotations'],1)
        self.assertGreater(result['diagnostics']['suppressed_rotations'],0)

    def test_rotation_gate_rejects_radial_drift_and_close_radius(self):
        self.assertEqual(self.m.virtual_rotation_delta([.2,0],[.201,.0001]),0.)
        self.assertEqual(self.m.virtual_rotation_delta([.009,0],[.01,.01]),0.)

    def test_small_integer_arc_can_have_geometric_effect_but_no_native_rotation(self):
        gesture=grouped_rotation_gesture(self.geometry.board,.05)
        self.assertTrue(gesture.has_effect)
        result=self.replay([gesture.record()])
        self.assertEqual(result['final_pose']['rotation_degrees'],0.)
        self.assertEqual(result['diagnostics']['accepted_rotations'],0)

    def test_zero_rotation_preserves_unwrapped_multi_turn_reference(self):
        reference=dict(self.reference,rotation_degrees=725.)
        result=self.m.replay_native_route(reference,[],self.geometry,self.settings,
                                          sample_policy='all_recorded_points')
        self.assertEqual(result['final_pose']['rotation_degrees'],725.)

    def test_explicit_wheel_mapping_and_same_pivot_pair_are_not_inverse(self):
        route=[wheel_gesture(self.geometry.board,1).record(),wheel_gesture(self.geometry.board,-1).record()]
        result=self.replay(route,wheel_delta_per_step=-1.)
        self.assertEqual(result['final_pose']['scale'],0.9998999834060669)

    def test_wheel_is_rejected_without_adapter_calibration(self):
        with self.assertRaises(ValueError):
            self.replay([wheel_gesture(self.geometry.board,1).record()])

    def test_sparse_sampling_can_change_rotation_and_records_assumptions(self):
        gesture=grouped_rotation_gesture(self.geometry.board,2).record()
        all_points=self.replay([gesture])
        indices=[0,8,len(gesture['points'])-1]
        sparse=self.m.replay_native_route(self.reference,[gesture],self.geometry,self.settings,
                                          sample_policy='explicit_indices',sample_indices=[indices])
        self.assertNotEqual(sparse['final_pose'],all_points['final_pose'])
        self.assertFalse(sparse['execution_verified'])
        self.assertFalse(sparse['game_response_verified'])
        self.assertFalse(sparse['release_inertia_modelled'])
        self.assertEqual(sparse['sample_policy'],'explicit_indices')

    def test_missing_first_sample_or_out_of_order_indices_fail_closed(self):
        gesture=drag_gesture(self.geometry.board,7,0).record()
        for indices in [[1,2],[0,2,1],[0,0,2]]:
            with self.assertRaises(ValueError):
                self.m.replay_native_route(self.reference,[gesture],self.geometry,self.settings,
                                           sample_policy='explicit_indices',sample_indices=[indices])

    def test_unknown_kind_and_nonfinite_input_are_rejected(self):
        for gesture in [dict(kind='click',points=[[450,450]]),dict(kind='drag',points=[[450,450],[float('nan'),450]])]:
            with self.assertRaises(ValueError):self.replay([gesture])
        with self.assertRaises(ValueError):
            self.m.apply_motion_event(self.reference,[.5,.5],[0,0],float('nan'),0,self.settings)

    def test_cancel_propagates_before_replay_output(self):
        def stop():raise InterruptedError('F9')
        with self.assertRaises(InterruptedError):self.replay([],check=stop)


if __name__=='__main__':unittest.main()
