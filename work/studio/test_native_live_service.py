"""Preflight must not construct a sender; user rules own live execution."""
import importlib,importlib.util,tempfile,threading,unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import MagicMock,patch


class NativeLiveServiceTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('native_live.service'),'Runner service missing')
        return importlib.import_module('native_live.service')
    def test_preflight_resolves_selected_process_without_sender_or_input(self):
        m=self.module();backend=MagicMock()
        backend.observe_window_context.return_value=dict(extent_one_to_one=True,window=dict(client_size_physical=[1280,960]))
        with tempfile.TemporaryDirectory() as tmp, patch.object(m,'CurrentBuildBackend',return_value=backend), \
             patch.object(m,'configure_ocr'),patch.object(m,'prepare_timer_assets',return_value={}), \
             patch.object(m,'prepare_hex_assets',return_value={}),patch.object(m,'read_input_backend',return_value={}), \
             patch.object(m,'ProjectClosedLoopIO') as adapter:
            result=m.preflight(123,Path(tmp),check=lambda:None)
        self.assertEqual(result['stop_reason'],'preflight_complete');self.assertEqual(result['actual_input_attempts'],0)
        adapter.assert_not_called();backend.close.assert_called_once()
    def test_no_active_new_session_never_constructs_sender(self):
        m=self.module();backend=MagicMock()
        backend.observe_window_context.return_value=dict(extent_one_to_one=True,window=dict(client_size_physical=[1280,960]))
        from window_target import WindowTarget
        target=WindowTarget(20,123,'Game','MabinogiMobile.exe')
        owner=MagicMock(stop=threading.Event())
        with tempfile.TemporaryDirectory() as tmp, patch.object(m,'resolve_target',return_value=target), \
             patch.object(m,'CurrentBuildBackend',return_value=backend),patch.object(m,'configure_ocr'), \
             patch.object(m,'prepare_timer_assets',return_value={}),patch.object(m,'prepare_hex_assets',return_value={}), \
             patch.object(m,'read_input_backend',return_value={}), \
             patch.object(m,'collect_validation_session',return_value=dict(stop_reason='already_active_palette')) as collect, \
             patch.object(m,'ProjectClosedLoopIO') as adapter:
            owner.folder=Path(tmp)
            result=m.run_native_search(owner,[dict(enabled=True,exact=True,colors=['#000000'],tolerance=0)]*3,target=target)
        self.assertEqual(result['stop_reason'],'already_active_palette');adapter.assert_not_called()
        self.assertTrue(any(call.args[0]=='native_result' for call in owner.event.call_args_list))
        self.assertEqual(collect.call_args.kwargs['session_seconds'],110.)

    def test_active_palette_at_start_is_bound_instead_of_rejected(self):
        from native_live.collect_dye_validation import collect_validation_session
        class ActiveBackend:
            def __init__(self): self.probed = []
            def process_identity(self): return [7, 8, 9, 'build']
            def observe_window_context(self, *args, **kwargs):
                return {'extent_one_to_one': True, 'window': {'client_size_physical': [1280, 960]}}
            def discover(self, *args, **kwargs): return 123
            def probe(self, address, *args, **kwargs):
                return {'active': True, 'session_token': ['same'], 'pose': {'position': [0, 0], 'scale': 1, 'rotation_degrees': 0}}
            def capture_validation_bundle(self, address, *args, **kwargs):
                return {'session_binding_verified': True, 'process_identity': [7, 8, 9, 'build'],
                        'session_token': ['same'], 'capture_folder': 'unused',
                        'pose': {'position': [0, 0], 'scale': 1, 'rotation_degrees': 0},
                        'cpu_comparison': {'client_float_hex_equal': True, 'float_within_tolerance': True}}
            def observe_motion(self, *args, **kwargs):
                return {'active': True, 'session_token': ['same'], 'process_identity': [7, 8, 9, 'build'],
                        'motion': {'pose': {'position': [0, 0], 'scale': 1, 'rotation_degrees': 0},
                                   'animators_done': True, 'binding': {}, 'settings': {}},
                        'geometry_diagnostic': {'rect': {'cache': {'local_refresh_pending': False,
                                                                     'cache_origin_consistent': True}}},
                        'window_mapping_candidate': {'client_board_candidate': [0, 0, 1280, 960]},
                        'window_context': {'window': {'client_size_physical': [1280, 960]}}}
        now=[1.]
        result=collect_validation_session(ActiveBackend(), wait_seconds=1, session_seconds=1,
            poll_seconds=.1, dwell_seconds=.1, clock=lambda: now[0], pause=lambda seconds: now.__setitem__(0, now[0]+seconds))
        self.assertEqual(result['stop_reason'], 'passive_baseline_collected')
        self.assertTrue(result['existing_active_palette'])
        self.assertEqual(result['instance_address'], 123)

    def test_action_kind_is_forwarded_without_colliding_with_runner_event_kind(self):
        m=self.module();events=[]
        def runner_event(kind,**data):events.append((kind,data))
        owner=SimpleNamespace(event=runner_event,stop=threading.Event())
        folder=Path(tempfile.mkdtemp())
        try:
            # Exercise the service event adapter through a minimal run setup.
            target=__import__('window_target').WindowTarget(20,123,'Game','MabinogiMobile.exe')
            backend=MagicMock();backend.observe_window_context.return_value=dict(extent_one_to_one=True,window=dict(client_size_physical=[1280,960]))
            def fake_loop(adapter,session,settings,rules,**kwargs):
                kwargs['event']({'event':'action','kind':'wheel','purpose':'compromise','at_monotonic':1.0})
                return {'stop_reason':'not_found_in_budget','actual_input_attempts':0,'accepted':False,
                        'verified':False,'actual_colors':[None]*3,'actual_deltas':[None]*3}
            with patch.object(m,'resolve_target',return_value=target), \
                 patch.object(m,'CurrentBuildBackend',return_value=backend), \
                 patch.object(m,'configure_ocr'), \
                 patch.object(m,'prepare_timer_assets',return_value={}), \
                 patch.object(m,'prepare_hex_assets',return_value={}), \
                 patch.object(m,'read_input_backend',return_value={}), \
                 patch.object(m,'collect_validation_session',return_value=dict(
                     stop_reason='passive_baseline_collected',capture={'capture_folder':'unused'},
                     baseline={'motion':{'settings':{} } },session_deadline_monotonic=100.0)), \
                 patch.object(m,'load_session',return_value={}), \
                 patch.object(m,'InputSettings',return_value={}), \
                 patch.object(m,'ProjectClosedLoopIO',return_value=SimpleNamespace(input_attempts=0,release=lambda:None)), \
                 patch.object(m,'run_goal_loop',side_effect=fake_loop):
                owner.folder=folder;owner.stop=threading.Event()
                result=m.run_native_search(owner,[dict(enabled=True,exact=True,colors=['#000000'],tolerance=0)]*3,target=target)
            calls=[data for kind,data in events if kind=='native_progress']
            self.assertTrue(calls)
            self.assertEqual(calls[-1]['action_kind'],'wheel')
            self.assertNotEqual(result['stop_reason'],'observation_failed')
        finally:
            import shutil;shutil.rmtree(folder,ignore_errors=True)


if __name__=='__main__':unittest.main()
