"""Transient reader cursor observations must not replace stable window binding."""
import json,tempfile,unittest
import copy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock,patch
from native_live import native_provider_backend as backend_module
from native_live import service
from native_live.dye_action_checkpoint import _binding,record_action_checkpoint
from test_support import requires_local_fixture


class NativeCursorDiagnosticIntegrationTests(unittest.TestCase):
    def test_recorded_remote_lattice_survives_reader_cursor_disagreement_without_replacing_it(self):
        from native_live.read_dye_window_mapping import validate_pixel_mapping
        source=Path(__file__).parent/'fixtures/native_live/rc15_remote_175/preparation.json'
        requires_local_fixture(source)
        data=json.loads(source.read_text(encoding='utf8'));context=data['window_context']
        mapping=context['pixel_mapping'];window=context['window'];screen=context['unity_screen']
        from contextlib import nullcontext
        class RecordedAPI:
            def target_context(self,hwnd):return nullcontext()
            def client_size(self,hwnd):return mapping['target_client_size']
            def client_to_physical(self,hwnd,point):
                return next(e['physical_screen'] for e in mapping['edge_samples'] if e['target_client']==list(point))
            def physical_to_client(self,hwnd,point):
                x,y=[int(v-o) for v,o in zip(point,window['client_origin_physical'])]
                return [mapping['target_client_x_by_physical_x'][x],mapping['target_client_y_by_physical_y'][y]]
            def cursor_check(self,hwnd):return dict(stationary=True,matches=False,
                physical_before=[2970,1409],physical_after=[2970,1409],
                reader_cursor_target_client=[810,726],converted_target_client=[809,726],target_client_delta=[1,0])
        original=copy.deepcopy(mapping);diagnostics={}
        self.assertTrue(validate_pixel_mapping(mapping,window,screen,10.,clock=lambda:1.,api=RecordedAPI(),diagnostics=diagnostics))
        self.assertEqual(mapping,original)
        self.assertEqual(diagnostics['cursor_route']['status'],'mismatch_in_reader_context')
        self.assertFalse(mapping['coordinate_validation']['stationary_route_verified'])

    def test_maximized_remote_extents_pass_axis_checks_even_when_reader_cursor_differs(self):
        from native_live.read_dye_window_mapping import read_pixel_mapping
        from test_native_window_mapping import MappingAPI
        source=Path(__file__).parent/'fixtures/native_live/rc15_remote_175/maximized-window.json'
        requires_local_fixture(source)
        context=json.loads(source.read_text(encoding='utf8'))
        window=context['window'];screen=context['unity_screen']
        api=MappingAPI(tuple(window['client_size_physical']),tuple(screen['size']),tuple(window['client_origin_physical']))
        api.bad_cursor=True;diagnostics={}
        mapping=read_pixel_mapping(window,screen,10.,clock=lambda:1.,api=api,diagnostics=diagnostics)
        self.assertEqual(mapping['physical_client_size'],[3840,2050])
        self.assertEqual(mapping['native_screen_size'],[2194,1171])
        self.assertTrue(mapping['coordinate_validation']['axis_separability_verified'])
        self.assertEqual(diagnostics['cursor_route']['status'],'mismatch_in_reader_context')
    def test_cursor_diagnostic_is_outside_window_identity_and_refresh_is_recorded(self):
        b=object.__new__(backend_module.CurrentBuildBackend)
        b.reader=SimpleNamespace(guard=lambda:None);b.unityplayer_version='fixture';b.window_hwnd=10
        b.build_files={};b.process_identity=lambda:(20,1,0x10000,'hash')
        w=dict(hwnd=10,pid=20,client_size_physical=[2240,1680],client_origin_physical=[1554,138],
            dpi=96,window_dpi_awareness=0,visible=True,minimized=False,physical_coordinates=True)
        s=dict(size=[1280,960],hwnd=10)
        lattice=dict(source='win32_target_awareness_pixel_lattice',coordinate_validation=dict(verified=True))
        def collect(*args,**kwargs):
            kwargs['diagnostics'].update(reader_cursor=dict(matches=False,physical_cursor_before=[2970,1409]))
            return lattice
        def refresh(*args,**kwargs):
            kwargs['diagnostics'].update(reader_cursor=dict(matches=False,physical_cursor_before=[3200,1409]))
            return True
        with patch.object(backend_module,'unityplayer_module_base',return_value=0x10000), \
            patch.object(backend_module,'read_unity_screen_extent',return_value=s), \
            patch.object(backend_module,'read_window_state',return_value=w), \
            patch.object(backend_module,'read_pixel_mapping',side_effect=collect), \
            patch.object(backend_module,'validate_pixel_mapping',side_effect=refresh):
            first=b.observe_window_context(10.,lambda:None,clock=lambda:1.,window_api=SimpleNamespace())
            observed1=b.last_pixel_mapping_diagnostic.copy()
            second=b.observe_window_context(10.,lambda:None,clock=lambda:1.,window_api=SimpleNamespace())
        self.assertEqual(first,second)
        self.assertNotIn('reader_cursor',first)
        self.assertNotEqual(observed1,b.last_pixel_mapping_diagnostic)
        self.assertEqual(b.last_pixel_mapping_diagnostic['reader_cursor']['physical_cursor_before'],[3200,1409])

    def test_preparation_records_cursor_data_for_later_remote_audit(self):
        backend=MagicMock();backend.last_pixel_mapping_diagnostic=dict(reader_cursor=dict(matches=False,delta=[1,0]))
        backend.observe_window_context.return_value=dict(extent_one_to_one=True,
            window=dict(client_size_physical=[1280,960]))
        with tempfile.TemporaryDirectory() as tmp,patch.object(service,'CurrentBuildBackend',return_value=backend), \
            patch.object(service,'configure_ocr'),patch.object(service,'prepare_timer_assets',return_value={}), \
            patch.object(service,'prepare_hex_assets',return_value={}),patch.object(service,'read_input_backend',return_value={}):
            result=service.preflight(20,Path(tmp))
            saved=json.loads((Path(tmp)/'native-preparation.json').read_text(encoding='utf8'))
        self.assertEqual(result['stop_reason'],'preflight_complete')
        self.assertEqual(saved['pixel_mapping_diagnostics']['reader_cursor']['delta'],[1,0])

    def test_native_mouse_cache_is_saved_as_diagnostic_and_never_changes_lattice_selection(self):
        b=object.__new__(backend_module.CurrentBuildBackend)
        b.reader=SimpleNamespace(guard=lambda:None);b.unityplayer_version='fixture';b.window_hwnd=10
        b.build_files={};b.process_identity=lambda:(20,1,0x10000,'hash')
        w=dict(hwnd=10,pid=20,client_size_physical=[2240,1680],client_origin_physical=[1554,138],
            visible=True,minimized=False,physical_coordinates=True)
        s=dict(size=[1280,960],hwnd=10)
        lattice=dict(source='win32_target_awareness_pixel_lattice',coordinate_validation=dict(verified=True))
        cached=dict(status='cache_collected',cached_mouse_unity=[809.,233.],freshness_verified=False)
        with patch.object(backend_module,'unityplayer_module_base',return_value=0x10000), \
            patch.object(backend_module,'read_unity_screen_extent',return_value=s), \
            patch.object(backend_module,'read_window_state',return_value=w), \
            patch.object(backend_module,'read_pixel_mapping',return_value=lattice), \
            patch.object(backend_module,'read_native_mouse_cache',return_value=cached,create=True) as read:
            context=b.observe_window_context(10.,lambda:None,clock=lambda:1.,window_api=SimpleNamespace())
        read.assert_called_once()
        self.assertEqual(b.last_pixel_mapping_diagnostic['native_mouse_cache'],cached)
        self.assertEqual(context['pixel_mapping'],lattice)
        self.assertNotIn('native_mouse_cache',context)

    def test_checkpoint_keeps_cursor_observations_without_invalidating_stable_motion(self):
        import copy
        import test_native_live_controller as fixture
        io=fixture.FixtureIO();raw=json.loads(io.cp['binding'])
        row=dict(active=True,session_token=raw[0],process_identity=raw[1],
            motion=dict(binding=raw[2],settings=raw[3],pose=copy.deepcopy(io.pose),animators_done=True),
            geometry_diagnostic=dict(rect=dict(cache=dict(local_refresh_pending=False,cache_origin_consistent=True))),
            window_mapping_candidate=dict(client_board_candidate=io.cp['board']),window_context=raw[4])
        captured=dict(session_binding_verified=True,session_token=raw[0],process_identity=raw[1],pose=copy.deepcopy(io.pose))
        tick=[1.];backend=SimpleNamespace(last_pixel_mapping_diagnostic={'reader_cursor':{'delta':[1,0]}},
            observe_motion=lambda *a,**k:copy.deepcopy(row),capture_validation_bundle=lambda *a,**k:copy.deepcopy(captured))
        result=record_action_checkpoint(backend,dict(baseline=row,session_deadline_monotonic=20.,instance_address=1),
            'diagnostic',dwell_seconds=.1,poll_seconds=.1,clock=lambda:tick[0],pause=lambda dt:tick.__setitem__(0,tick[0]+dt))
        self.assertTrue(result['checkpoint_valid'])
        self.assertEqual(result['pixel_mapping_diagnostics']['reader_cursor']['delta'],[1,0])
        self.assertEqual(_binding(result['observation']),_binding(row))


if __name__=='__main__':unittest.main()
