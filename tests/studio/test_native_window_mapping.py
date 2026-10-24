"""Exact per-pixel Win32 target-awareness maps without game input."""
import importlib
import importlib.util
import math
import unittest
from contextlib import contextmanager


class MappingAPI:
    def __init__(self,physical=(12,9),logical=(8,6),origin=(-150,45)):
        self.physical=physical;self.logical=logical;self.origin=origin
        self.context=False;self.entered=0;self.calls=0
        self.changed=False;self.skew=False;self.bad_cursor=False
        self.cursor_outside=False
        self.shift_after_edges=False;self.edge_calls=0
    @contextmanager
    def target_context(self,hwnd):
        prior=self.context;self.context=True;self.entered+=1
        try:yield
        finally:self.context=prior
    def client_size(self,hwnd):
        if not self.context:raise AssertionError('Wrong reader awareness context')
        return list(self.logical)
    def physical_to_client(self,hwnd,point):
        if not self.context:raise AssertionError('Wrong conversion awareness context')
        self.calls+=1
        x=math.floor((point[0]-self.origin[0])*self.logical[0]/self.physical[0])
        y=math.floor((point[1]-self.origin[1])*self.logical[1]/self.physical[1])
        if self.changed and self.calls>200:x+=1
        if self.skew:x+=int(point[1]!=self.origin[1])
        return [x,y]
    def client_to_physical(self,hwnd,point):
        result=[self.origin[0]+round(point[0]*self.physical[0]/self.logical[0]),
                self.origin[1]+round(point[1]*self.physical[1]/self.logical[1])]
        self.edge_calls+=1
        if self.shift_after_edges and self.edge_calls==4:self.origin=(self.origin[0]-1,self.origin[1]-1)
        return result
    def cursor_check(self,hwnd):
        if self.cursor_outside:return dict(stationary=False,matches=False,reason='cursor_outside_selected_client')
        return dict(stationary=True,matches=not self.bad_cursor)


class NativeWindowMappingTests(unittest.TestCase):
    def setUp(self):
        self.api=MappingAPI()
        self.window=dict(hwnd=10,pid=20,client_origin_physical=[-150,45],client_size_physical=[12,9],
          window_dpi_awareness=0,physical_coordinates=True,visible=True,minimized=False)
        self.screen=dict(size=[8,6],source='current_build_native_screen_fields')
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('native_live.read_dye_window_mapping'),'DPI pixel mapper missing')
        return importlib.import_module('native_live.read_dye_window_mapping')
    def read(self,**kwargs):
        return self.module().read_pixel_mapping(self.window,self.screen,10.,lambda:None,clock=lambda:0.,api=self.api,**kwargs)
    def test_exact_150_percent_lattice_contains_duplicate_mouse_pixels(self):
        result=self.read()
        self.assertEqual(result['target_client_x_by_physical_x'],[0,0,1,2,2,3,4,4,5,6,6,7])
        self.assertEqual(result['target_client_y_by_physical_y'],[0,0,1,2,2,3,4,4,5])
        self.assertEqual(result['physical_client_size'],[12,9]);self.assertEqual(result['native_screen_size'],[8,6])
        self.assertTrue(result['coordinate_validation']['verified']);self.assertFalse(self.api.context)
    def test_same_extent_maps_identity_independent_of_negative_desktop_origin(self):
        self.api=MappingAPI((8,6),(8,6));self.window['client_size_physical']=[8,6]
        result=self.read()
        self.assertEqual(result['target_client_x_by_physical_x'],list(range(8)))
        self.assertEqual(result['target_client_y_by_physical_y'],list(range(6)))
    def test_fractional_dpi_ratios_follow_api_integer_results(self):
        for physical,expected in (((10,10),[0,0,1,2,3,4,4,5,6,7]),
                                  ((14,14),[0,0,1,1,2,2,3,4,4,5,5,6,6,7]),
                                  ((16,16),[0,0,1,1,2,2,3,3,4,4,5,5,6,6,7,7])):
            self.api=MappingAPI(physical,(8,8));self.window['client_size_physical']=list(physical)
            self.screen['size']=[8,8]
            self.assertEqual(self.read()['target_client_x_by_physical_x'],expected)
    def test_nonseparable_conversion_is_rejected(self):
        self.api.skew=True
        with self.assertRaises(ValueError):self.read()
        self.assertFalse(self.api.context)
    def test_native_extent_must_match_target_client_units(self):
        self.screen['size']=[12,9]
        with self.assertRaises(ValueError):self.read()
    def test_reader_cursor_disagreement_is_diagnostic_while_axis_proof_remains_valid(self):
        self.api.bad_cursor=True
        diagnostics={};result=self.read(diagnostics=diagnostics)
        self.assertTrue(result['coordinate_validation']['verified'])
        self.assertFalse(result['coordinate_validation']['stationary_route_verified'])
        self.assertEqual(result['coordinate_validation']['reader_cursor_route_status'],'mismatch_in_reader_context')
        self.assertEqual(diagnostics['cursor_route']['status'],'mismatch_in_reader_context')
        validated={}
        self.assertTrue(self.module().validate_pixel_mapping(result,self.window,self.screen,10.,lambda:None,
          clock=lambda:0.,api=self.api,diagnostics=validated))
        self.assertEqual(validated['cursor_route']['status'],'mismatch_in_reader_context')

    def test_optional_cursor_api_failure_is_saved_without_discarding_verified_axes(self):
        def failed(*args):raise OSError('GetCursorPos failed in reader')
        self.api.cursor_check=failed;diagnostics={}
        result=self.read(diagnostics=diagnostics)
        self.assertTrue(result['coordinate_validation']['verified'])
        self.assertFalse(result['coordinate_validation']['stationary_route_verified'])
        self.assertEqual(diagnostics['cursor_route']['status'],'reader_cursor_unavailable')
    def test_cursor_diagnostic_does_not_swallow_stop_or_deadline(self):
        for failure in (InterruptedError('F9'),TimeoutError('deadline')):
            def failed(*args):raise failure
            self.api.cursor_check=failed
            with self.assertRaises(type(failure)):self.read(diagnostics={})
    def test_cursor_outside_selected_window_does_not_block_axis_proof(self):
        self.api.cursor_outside=True
        result=self.read()
        self.assertTrue(result['coordinate_validation']['verified'])
        self.assertFalse(result['coordinate_validation']['stationary_route_verified'])
        self.assertEqual(result['coordinate_validation']['reason'],'cursor_outside_selected_client')
    def test_modified_unsampled_axis_pixel_invalidates_cached_fingerprint(self):
        result=self.read();result['target_client_x_by_physical_x'][5]=99
        with self.assertRaises(ValueError):self.module().validate_pixel_mapping(result,self.window,self.screen,10.,lambda:None,clock=lambda:0.,api=self.api)
    def test_window_move_after_initial_edges_prevents_mapping_publication(self):
        self.api.shift_after_edges=True
        with self.assertRaises(ValueError):self.read()
        self.assertFalse(self.api.context)
    def test_deadline_and_stop_restore_awareness_context(self):
        module=self.module()
        with self.assertRaises(TimeoutError):
            module.read_pixel_mapping(self.window,self.screen,0.,lambda:None,clock=lambda:0.,api=self.api)
        def stop():raise InterruptedError('stop')
        with self.assertRaises(InterruptedError):
            module.read_pixel_mapping(self.window,self.screen,10.,stop,clock=lambda:0.,api=self.api)
        self.assertFalse(self.api.context)
    def test_fast_validation_reuses_bound_map_without_rebuilding_axes(self):
        result=self.read();self.api.calls=0
        self.assertTrue(self.module().validate_pixel_mapping(result,self.window,self.screen,10.,lambda:None,
          clock=lambda:0.,api=self.api))
        self.assertLess(self.api.calls,40)
    def test_changed_binding_and_changed_integer_sample_invalidate_cached_map(self):
        result=self.read();module=self.module()
        changed=dict(self.window,client_origin_physical=[-149,45])
        with self.assertRaises(ValueError):module.validate_pixel_mapping(result,changed,self.screen,10.,lambda:None,clock=lambda:0.,api=self.api)
        self.api.calls=201;self.api.changed=True
        with self.assertRaises(ValueError):module.validate_pixel_mapping(result,self.window,self.screen,10.,lambda:None,clock=lambda:0.,api=self.api)


if __name__=='__main__':unittest.main()
