"""Native screen reads use verified selected-process module paths and metadata."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import unittest
from native_live import native_provider_backend as module


class NativePortableBackendTests(unittest.TestCase):
    def backend(self):
        b=object.__new__(module.CurrentBuildBackend)
        b.reader=SimpleNamespace(guard=lambda:None);b.window_hwnd=1;b.unityplayer_version='verified'
        b.build_files={'unityplayer':Path('D:/游戏/UnityPlayer.dll')}
        b.process_identity=lambda:(2,3,4,'hash')
        return b
    def window(self,size):
        return dict(hwnd=1,pid=2,client_size_physical=size,client_origin_physical=[-2800,200],
            dpi=192,window_dpi_awareness=2,physical_coordinates=True)
    def test_native_screen_module_resolution_uses_actual_build_file(self):
        b=self.backend()
        with patch.object(module,'unityplayer_module_base',return_value=0x10000) as resolve, \
            patch.object(module,'read_unity_screen_extent',return_value=dict(size=[1280,960])), \
            patch.object(module,'read_window_state',return_value=self.window([1280,960])):
            context=b.observe_window_context(10.,lambda:None,clock=lambda:1.,window_api=SimpleNamespace())
        self.assertEqual(resolve.call_args.kwargs['expected_path'],b.build_files['unityplayer'])
        self.assertEqual(context['window']['dpi'],192)
        self.assertTrue(context['extent_one_to_one'])
    def test_mismatch_retains_actual_extents_and_dpi_without_guessing_scale(self):
        b=self.backend()
        with patch.object(module,'unityplayer_module_base',return_value=0x10000), \
            patch.object(module,'read_unity_screen_extent',return_value=dict(size=[1280,960])), \
            patch.object(module,'read_window_state',return_value=self.window([2560,1920])):
            with self.assertRaisesRegex(ValueError,'extents differ'):
                b.observe_window_context(10.,lambda:None,clock=lambda:1.,window_api=SimpleNamespace())
        self.assertFalse(b.last_window_diagnostic['extent_one_to_one'])
        self.assertEqual(b.last_window_diagnostic['unity_screen']['size'],[1280,960])
        self.assertEqual(b.last_window_diagnostic['window']['client_size_physical'],[2560,1920])
    def test_non_four_three_physical_window_works_when_native_extent_agrees(self):
        b=self.backend()
        with patch.object(module,'unityplayer_module_base',return_value=0x10000), \
            patch.object(module,'read_unity_screen_extent',return_value=dict(size=[3840,2160])), \
            patch.object(module,'read_window_state',return_value=self.window([3840,2160])):
            context=b.observe_window_context(10.,lambda:None,clock=lambda:1.,window_api=SimpleNamespace())
        self.assertTrue(context['extent_one_to_one'])
    def test_scaled_window_collects_and_reuses_verified_integer_mapping(self):
        b=self.backend();window=self.window([1920,1440]);window.update(visible=True,minimized=False)
        screen=dict(size=[1280,960],hwnd=1)
        mapping=dict(source='win32_target_awareness_pixel_lattice',coordinate_validation=dict(verified=True),
            physical_client_size=[1920,1440],native_screen_size=[1280,960])
        with patch.object(module,'unityplayer_module_base',return_value=0x10000), \
            patch.object(module,'read_unity_screen_extent',return_value=screen), \
            patch.object(module,'read_window_state',return_value=window), \
            patch.object(module,'read_pixel_mapping',return_value=mapping,create=True) as collect, \
            patch.object(module,'validate_pixel_mapping',return_value=True,create=True) as refresh:
            context=b.observe_window_context(10.,lambda:None,clock=lambda:1.,window_api=SimpleNamespace())
            repeated=b.observe_window_context(10.,lambda:None,clock=lambda:1.,window_api=SimpleNamespace())
        self.assertFalse(context['extent_one_to_one']);self.assertTrue(context['coordinate_mapping_verified'])
        self.assertEqual(context['pixel_mapping'],mapping);self.assertEqual(context,repeated)
        collect.assert_called_once();refresh.assert_called_once()
    def test_native_hwnd_mismatch_is_rejected_with_measured_context(self):
        b=self.backend()
        with patch.object(module,'unityplayer_module_base',return_value=0x10000), \
            patch.object(module,'read_unity_screen_extent',return_value=dict(size=[1280,960],hwnd=99)), \
            patch.object(module,'read_window_state',return_value=self.window([1280,960])):
            with self.assertRaisesRegex(ValueError,'window handle'):
                b.observe_window_context(10.,lambda:None,clock=lambda:1.,window_api=SimpleNamespace())
        self.assertEqual(b.last_window_diagnostic['unity_screen']['hwnd'],99)
    def test_partial_window_error_keeps_the_native_screen_and_failed_api_values(self):
        b=self.backend();failure=ValueError('Physical client extent mismatch')
        failure.diagnostic=dict(hwnd=1,pid=2,raw_client_rect=[0,0,1280,960],
            client_screen_endpoints=[[300,100],[2220,1540]])
        with patch.object(module,'unityplayer_module_base',return_value=0x10000), \
            patch.object(module,'read_unity_screen_extent',return_value=dict(size=[1280,960],hwnd=1)), \
            patch.object(module,'read_window_state',side_effect=failure):
            with self.assertRaises(ValueError):b.observe_window_context(10.,lambda:None,clock=lambda:1.,window_api=SimpleNamespace())
        self.assertEqual(b.last_window_diagnostic['window']['raw_client_rect'],[0,0,1280,960])
        self.assertEqual(b.last_window_diagnostic['unity_screen']['size'],[1280,960])
    def test_window_cannot_move_between_mapping_collection_and_publication(self):
        b=self.backend();window=self.window([1920,1440]);window.update(visible=True,minimized=False)
        moved=dict(window,client_origin_physical=[-2801,200])
        with patch.object(module,'unityplayer_module_base',return_value=0x10000), \
            patch.object(module,'read_unity_screen_extent',return_value=dict(size=[1280,960],hwnd=1)), \
            patch.object(module,'read_window_state',side_effect=[window,window,moved]), \
            patch.object(module,'read_pixel_mapping',return_value={'coordinate_validation':{'verified':True}}):
            with self.assertRaisesRegex(ValueError,'changed'):
                b.observe_window_context(10.,lambda:None,clock=lambda:1.,window_api=SimpleNamespace())


if __name__=='__main__':unittest.main()
