"""Catch planning from requested geometry instead of predicted accepted input."""
import importlib
import importlib.util
import unittest
import numpy as np
from native_input_response import InputGeometry, InputSettings, replay_native_route
from native_palette_pose import relative_board_pose
from atlas_pose import marker_errors


class NativeInputCompileTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('native_input_compile'),
                             'Stepwise native input compiler is missing')
        self.m=importlib.import_module('native_input_compile')
        self.geometry=InputGeometry((100,100,800,800),(624,624))
        self.settings=InputSettings(.5,3,5,.1,.01)
        self.reference=dict(position=[0.,0.],scale=1.,rotation_degrees=0.)
        self.markers=[[216,500],[450,500],[683,500]]

    def compile(self,target,**kwargs):
        return self.m.compile_native_route(target,self.reference,self.geometry,
            self.settings,self.markers,wheel_delta_per_step=1.,
            sample_policy='all_recorded_points',now=0.,deadline=120.,**kwargs)

    def test_identity_needs_no_input_and_keeps_validation_reserve(self):
        result=self.compile(self.reference)
        self.assertEqual(result['input_route'],[])
        self.assertTrue(result['allowed'])
        self.assertGreaterEqual(result['needed'],3.5)
        self.assertFalse(result['game_response_verified'])

    def test_micro_drag_crosses_threshold_then_returns_in_same_touch(self):
        gesture=self.m.native_drag_gesture(self.geometry,self.settings,1,0)
        self.assertEqual(gesture.translation,(1,0))
        self.assertGreater(max(p[0] for p in gesture.points)-gesture.points[0][0],5)
        result=replay_native_route(self.reference,[gesture.record()],self.geometry,
            self.settings,sample_policy='all_recorded_points')
        self.assertAlmostEqual(result['final_pose']['position'][0],1/700,places=7)

    def test_stepwise_compiler_reaches_micro_translation_with_real_response(self):
        target=dict(self.reference,position=[1/700,-2/700])
        result=self.compile(target)
        self.assertTrue(result['modelled_reached'])
        self.assertTrue(result['allowed'])
        self.assertLess(max(result['marker_errors']),.1)
        replay=replay_native_route(self.reference,result['input_route'],self.geometry,
                   self.settings,sample_policy='all_recorded_points',wheel_delta_per_step=1.)
        self.assertEqual(replay['final_pose'],result['final_pose'])

    def test_nonreciprocal_wheel_scale_reaches_point99_without_old_reciprocal_assumption(self):
        target=dict(self.reference,scale=.99)
        result=self.compile(target)
        self.assertTrue(result['modelled_reached'])
        self.assertAlmostEqual(result['final_pose']['scale'],.99,places=6)
        self.assertEqual(result['actions']['wheel'],1)

    def test_mixed_route_is_replanned_after_each_predicted_update(self):
        target=dict(position=[.07,-.025],scale=1.01,rotation_degrees=2.)
        result=self.compile(target,marker_tolerance=.3)
        self.assertTrue(result['modelled_reached'])
        target_matrix=relative_board_pose(target,self.reference,self.geometry.board)
        actual_matrix=relative_board_pose(result['final_pose'],self.reference,self.geometry.board)
        errors=marker_errors(target_matrix,actual_matrix,np.asarray(self.markers)-[100,100])
        self.assertLess(max(errors),.3)
        self.assertEqual(len(result['input_route']),len(result['steps']))
        for step in result['steps']:
            self.assertLess(step['after_max_error'],step['before_max_error'])

    def test_no_progress_is_not_reported_as_reached(self):
        target=dict(self.reference,rotation_degrees=.01)
        result=self.compile(target,marker_tolerance=1e-7,max_steps=2)
        self.assertFalse(result['modelled_reached'])
        self.assertFalse(result['allowed'])

    def test_expired_and_insufficient_time_fail_closed(self):
        result=self.m.compile_native_route(self.reference,self.reference,self.geometry,self.settings,
            self.markers,wheel_delta_per_step=1.,sample_policy='all_recorded_points',now=5,deadline=5)
        self.assertFalse(result['allowed'])
        self.assertEqual(result['reason'],'deadline')
        result=self.m.compile_native_route(self.reference,self.reference,self.geometry,self.settings,
            self.markers,wheel_delta_per_step=1.,sample_policy='all_recorded_points',now=0,deadline=2)
        self.assertFalse(result['allowed'])
        self.assertEqual(result['reason'],'insufficient_time')

    def test_proposal_limit_and_cancel_bound_planning(self):
        target=dict(position=[.3,.2],scale=1.2,rotation_degrees=20)
        result=self.compile(target,max_proposals=1)
        self.assertLessEqual(result['evaluated_proposals'],1)
        self.assertFalse(result['allowed'])
        def stop():raise InterruptedError('F9')
        with self.assertRaises(InterruptedError):self.compile(target,check=stop)

    def test_sparse_sampling_requires_explicit_measured_compiler_policy(self):
        with self.assertRaises(ValueError):
            self.m.compile_native_route(self.reference,self.reference,self.geometry,self.settings,
                self.markers,wheel_delta_per_step=1.,sample_policy='explicit_indices',now=0,deadline=120)

    def test_unavailable_safe_kick_does_not_abort_other_candidate_planning(self):
        geometry=InputGeometry(self.geometry.board,(1,1))
        target=dict(self.reference,position=[1/700,0.])
        result=self.m.compile_native_route(target,self.reference,geometry,self.settings,
            self.markers,wheel_delta_per_step=1.,sample_policy='all_recorded_points',now=0.,deadline=120.)
        self.assertFalse(result['allowed'])
        self.assertEqual(result['reason'],'no_modelled_progress')
        self.assertGreater(result['unavailable_drag_proposals'],0)


if __name__=='__main__':unittest.main()
