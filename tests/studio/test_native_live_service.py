from native_live.build_adapters import TW_ADAPTER
"""Preflight must not construct a sender; user rules own live execution."""
import importlib,importlib.util,tempfile,threading,unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import MagicMock,patch


class NativeLiveServiceTests(unittest.TestCase):
    def test_failed_cancel_diagnostic_cannot_hide_f9_or_leak_the_backend(self):
        m=self.module();closed=[];writes=[]
        def cancel(*args):raise InterruptedError('F9 fixture')
        backend=SimpleNamespace(build_files={},adapter=TW_ADAPTER,observe_window_context=cancel,close=lambda:closed.append(True))
        original=Path.write_text
        def write(path,*args,**kwargs):
            if path.name=='native-preparation.json':
                writes.append(True)
                if len(writes)==4:raise OSError('Diagnostic disk fixture failure')
            return original(path,*args,**kwargs)
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'configure_ocr'), \
             patch.object(m,'prepare_timer_assets',return_value={}),patch.object(m,'prepare_hex_assets',return_value={}), \
             patch.object(m,'CurrentBuildBackend',return_value=backend),patch.object(Path,'write_text',new=write):
            with self.assertRaisesRegex(InterruptedError,'F9 fixture'):m._prepare(123,Path(tmp),lambda:None,20)
            self.assertEqual(closed,[True])

    def test_cancelled_preparation_does_not_start_ocr_or_open_game(self):
        m=self.module()
        def cancelled():raise InterruptedError('Stop requested')
        prepared=SimpleNamespace(build_files={},adapter=TW_ADAPTER,close=lambda:None,
            observe_window_context=lambda *args:dict(extent_one_to_one=True,window=dict(client_size_physical=[1280,960])))
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'configure_ocr') as ocr, \
             patch.object(m,'prepare_timer_assets',return_value={}),patch.object(m,'prepare_hex_assets',return_value={}), \
             patch.object(m,'read_input_backend',return_value={}),patch.object(m,'CurrentBuildBackend',return_value=prepared) as backend:
            with self.assertRaises(InterruptedError):m._prepare(123,Path(tmp),cancelled,20)
            ocr.assert_not_called();backend.assert_not_called()

    def test_detected_f9_is_recorded_as_key_signal_without_claiming_a_button_click(self):
        from run_stop import StopEvent
        from window_target import WindowTarget
        m=self.module();backend=MagicMock();backend.adapter=TW_ADAPTER
        with tempfile.TemporaryDirectory() as tmp:
            owner=SimpleNamespace(folder=Path(tmp),stop=StopEvent(),event=MagicMock())
            def collect(*args,**kwargs):
                with patch.object(m.u,'GetAsyncKeyState',return_value=-32768):
                    try:kwargs['check']()
                    except InterruptedError as exc:return dict(stop_reason='interrupted',error=str(exc))
                self.fail('A detected F9 signal did not stop preparation')
            with patch.object(m,'resolve_target',return_value=WindowTarget(20,123,'Game','MabinogiMobile.exe')), \
                 patch.object(m,'_prepare',return_value=(backend,{})),patch.object(m,'collect_validation_session',side_effect=collect), \
                 patch.object(m.u,'GetAsyncKeyState',return_value=0):
                result=m.run_native_search(owner,[dict(enabled=True,exact=True,colors=['#FFFFFF'],tolerance=0)]*3)
            self.assertEqual(result['interruption_reason'],'stop_key_detected')
            self.assertEqual(result['stop_diagnostic']['source'],'native_f9_poll')
            self.assertEqual(result['stop_diagnostic']['key_state'],-32768)
            saved=__import__('json').loads((Path(tmp)/'native-result.json').read_text(encoding='utf-8'))
            self.assertEqual(saved['stop_diagnostic'],result['stop_diagnostic'])

    def test_preparation_interrupt_error_survives_final_result_without_assuming_user_stop(self):
        m=self.module();backend=MagicMock();backend.adapter=TW_ADAPTER
        from window_target import WindowTarget
        for error,want in [('internal cancellation','unknown_interruption'),
                           ('已暂停：游戏失去焦点。返回游戏后按 F8 重新开始。','focus_lost')]:
            with self.subTest(error=error),tempfile.TemporaryDirectory() as tmp:
                owner=SimpleNamespace(folder=Path(tmp),stop=threading.Event(),event=MagicMock())
                with patch.object(m,'resolve_target',return_value=WindowTarget(20,123,'Game','MabinogiMobile.exe')), \
                     patch.object(m,'_prepare',return_value=(backend,{})), \
                     patch.object(m,'collect_validation_session',return_value=dict(stop_reason='interrupted',error=error)):
                    result=m.run_native_search(owner,[dict(enabled=True,exact=True,colors=['#FFFFFF'],tolerance=0)]*3)
                self.assertEqual(result.get('error'),error)
                self.assertEqual(result.get('interruption_reason'),want)

    def test_start_button_activation_is_used_before_waiting_for_the_board(self):
        m=self.module();backend=MagicMock();backend.adapter=TW_ADAPTER
        from window_target import WindowTarget
        target=WindowTarget(20,123,'Game','MabinogiMobile.exe');order=[]
        with tempfile.TemporaryDirectory() as tmp:
            owner=SimpleNamespace(folder=Path(tmp),stop=threading.Event(),event=MagicMock())
            def activate(selected,**kwargs):kwargs['check']();order.append('activate');self.assertEqual(selected,target);return True
            def collect(*a,**k):order.append('collect');return dict(stop_reason='no_active_palette_timeout')
            with patch.object(m,'resolve_target',return_value=target),patch.object(m,'_prepare',return_value=(backend,{})), \
                patch('window_target.activate_target_window',side_effect=activate),patch.object(m,'collect_validation_session',side_effect=collect):
                result=m.run_native_search(owner,[dict(enabled=True,exact=True,colors=['#FFFFFF'],tolerance=8)]*3,activate=True)
            self.assertEqual(order,['activate','collect'])
            self.assertEqual(result['actual_input_attempts'],0)

    def test_start_restores_minimized_window_before_measuring_geometry(self):
        m=self.module();backend=MagicMock();backend.adapter=TW_ADAPTER
        from window_target import WindowTarget
        target=WindowTarget(20,123,'Game','MabinogiMobile.exe');visible=[False]
        def activate(selected,**kwargs):kwargs['check']();visible[0]=True;return True
        def prepare(*args):
            if not visible[0]:raise ValueError('Invalid target-context client bounds')
            return backend,{}
        with tempfile.TemporaryDirectory() as tmp:
            owner=SimpleNamespace(folder=Path(tmp),stop=threading.Event(),event=MagicMock())
            with patch.object(m,'resolve_target',return_value=target),patch.object(m,'_prepare',side_effect=prepare), \
                patch('window_target.activate_target_window',side_effect=activate), \
                patch.object(m,'collect_validation_session',return_value=dict(stop_reason='no_active_palette_timeout')):
                result=m.run_native_search(owner,[dict(enabled=True,exact=True,colors=['#FFFFFF'],tolerance=0)]*3,activate=True)
            self.assertEqual(result['stop_reason'],'no_active_palette_timeout',result.get('error'))
            self.assertEqual(result['actual_input_attempts'],0)

    def test_ready_wait_and_active_binding_have_distinct_progress(self):
        m=self.module();backend=MagicMock();backend.adapter=TW_ADAPTER
        from window_target import WindowTarget
        target=WindowTarget(20,123,'Game','MabinogiMobile.exe');events=[]
        with tempfile.TemporaryDirectory() as tmp:
            owner=SimpleNamespace(folder=Path(tmp),stop=threading.Event(),event=lambda kind,**data:events.append((kind,data)))
            def collect(*a,**k):
                k['event'](dict(event='armed',existing_active_palette=False))
                k['event'](dict(event='discovery_progress',phase='waiting',discovery={'eligible_addresses':[]}))
                k['event'](dict(event='discovery_progress',phase='waiting',discovery={'eligible_addresses':['0x10000']}))
                return dict(stop_reason='no_active_palette_timeout')
            with patch.object(m,'resolve_target',return_value=target),patch.object(m,'_prepare',return_value=(backend,{})), \
                patch.object(m,'collect_validation_session',side_effect=collect):
                m.run_native_search(owner,[dict(enabled=True,exact=True,colors=['#FFFFFF'],tolerance=8)]*3)
            progress=[d for kind,d in events if kind=='native_progress']
            self.assertTrue(all('已就绪' in (d['message'] or '') for d in progress[-3:-1]))
            self.assertEqual(progress[-1]['stage'],'binding')
            self.assertIn('前台',progress[-1]['message'])

    def test_focus_stop_reason_reaches_result_presentation(self):
        m=self.module();backend=MagicMock();backend.adapter=TW_ADAPTER
        from window_target import WindowTarget
        target=WindowTarget(20,123,'Game','MabinogiMobile.exe');events=[]
        with tempfile.TemporaryDirectory() as tmp:
            owner=SimpleNamespace(folder=Path(tmp),stop=threading.Event(),event=lambda kind,**data:events.append((kind,data)))
            with patch.object(m,'resolve_target',return_value=target),patch.object(m,'_prepare',return_value=(backend,{})), \
                patch.object(m,'collect_validation_session',side_effect=InterruptedError('已暂停：游戏失去焦点。返回游戏后按 F8 重新开始。')):
                result=m.run_native_search(owner,[dict(enabled=True,exact=True,colors=['#FFFFFF'],tolerance=8)]*3)
            self.assertEqual(result.get('interruption_reason'),'focus_lost')
            shown=next(d for k,d in events if k=='native_result')
            from native_status import result_text
            self.assertIn('焦点',result_text(shown)[0])

    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('native_live.service'),'Runner service missing')
        return importlib.import_module('native_live.service')
    def test_preflight_resolves_selected_process_without_sender_or_input(self):
        m=self.module();backend=MagicMock();backend.adapter=TW_ADAPTER
        backend.observe_window_context.return_value=dict(extent_one_to_one=True,window=dict(client_size_physical=[1280,960]))
        with tempfile.TemporaryDirectory() as tmp, patch.object(m,'CurrentBuildBackend',return_value=backend), \
             patch.object(m,'configure_ocr'),patch.object(m,'prepare_timer_assets',return_value={}), \
             patch.object(m,'prepare_hex_assets',return_value={}),patch.object(m,'read_input_backend',return_value={}), \
             patch.object(m,'ProjectClosedLoopIO') as adapter:
            result=m.preflight(123,Path(tmp),check=lambda:None)
        self.assertEqual(result['stop_reason'],'preflight_complete');self.assertEqual(result['actual_input_attempts'],0)
        adapter.assert_not_called();backend.close.assert_called_once()
    def test_no_active_new_session_never_constructs_sender(self):
        m=self.module();backend=MagicMock();backend.adapter=TW_ADAPTER
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
        self.assertEqual(collect.call_args.kwargs['session_seconds'],117.)

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
            backend=MagicMock();backend.adapter=TW_ADAPTER;backend.observe_window_context.return_value=dict(extent_one_to_one=True,window=dict(client_size_physical=[1280,960]))
            def fake_loop(adapter,session,settings,rules,**kwargs):
                for name in ('refinement_planning','refinement_search_progress'):
                    kwargs['event'](dict(event=name,stage='integer_drags',examined=14527,
                        current_colors=['#FFFFFF','#FFFFFF','#EBEEDC'],current_deltas=[0.,0.,11.45],
                        verified=True,screenshot_verified=True))
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
                 patch.object(m,'load_session',return_value=dict(pixels=[None]*3,picker_uv=[[1/6,.5],[.5,.5],[5/6,.5]])), \
                 patch.object(m,'InputSettings',return_value={}), \
                 patch.object(m,'ProjectClosedLoopIO',return_value=SimpleNamespace(input_attempts=0,release=lambda:None)), \
                 patch.object(m,'run_goal_loop',side_effect=fake_loop):
                owner.folder=folder;owner.stop=threading.Event()
                result=m.run_native_search(owner,[dict(enabled=True,exact=True,colors=['#000000'],tolerance=0)]*3,target=target)
            calls=[data for kind,data in events if kind=='native_progress']
            self.assertTrue(calls)
            self.assertEqual(calls[-1]['action_kind'],'wheel')
            refinement=[row for row in calls if row.get('stage')=='refinement']
            self.assertEqual(len(refinement),2)
            for row in refinement:
                self.assertEqual(row['current_colors'],['#FFFFFF','#FFFFFF','#EBEEDC'])
                self.assertEqual(row['current_deltas'],[0.,0.,11.45])
                self.assertTrue(row['verified'] and row['screenshot_verified'])
            self.assertNotEqual(result['stop_reason'],'observation_failed')
        finally:
            import shutil;shutil.rmtree(folder,ignore_errors=True)


if __name__=='__main__':unittest.main()
