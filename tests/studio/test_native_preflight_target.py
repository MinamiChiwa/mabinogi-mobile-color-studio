"""Read-only CLI must preserve the selected HWND, including high-DPI windows."""
import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import native_preflight
from window_target import WindowTarget


class NativePreflightTargetTests(unittest.TestCase):
    def test_japanese_locator_keeps_handle_with_other_servers_running(self):
        windows=[WindowTarget(30,40,'瑪奇 Mobile','MabinogiMobile.exe'),
            WindowTarget(50,60,'마비노기 모바일','MabinogiMobile.exe'),WindowTarget(70,80,'マビモバ','MabinogiMobile.exe')]
        result={'stop_reason':'preflight_complete','build_adapter':{'adapter_id':'jp-20261012-research-candidate'}}
        with tempfile.TemporaryDirectory() as tmp,patch('window_target.list_windows',return_value=windows), \
            patch('native_live.service.preflight',return_value=result) as preflight:
            self.assertEqual(native_preflight.main(['--japanese','--output-dir',tmp]),0)
        self.assertEqual(preflight.call_args.args,(80,Path(tmp)))
        self.assertEqual(preflight.call_args.kwargs['hwnd'],70)

    def test_japanese_locator_rejects_other_build_under_japanese_title(self):
        result={'stop_reason':'preflight_complete','build_adapter':{'adapter_id':'kr-20261012-research-candidate'}}
        with tempfile.TemporaryDirectory() as tmp,patch('window_target.list_windows',return_value=[WindowTarget(70,80,'マビモバ','MabinogiMobile.exe')]), \
            patch('native_live.service.preflight',return_value=result):
            self.assertEqual(native_preflight.main(['--japanese','--output-dir',tmp]),1)
            import json
            self.assertEqual(json.loads((Path(tmp)/'native-preflight.json').read_text())['unavailable_reason'],'game_build')

    def test_automatic_target_preserves_handle_in_preflight(self):
        with tempfile.TemporaryDirectory() as tmp,patch('window_target.resolve_target',return_value=WindowTarget(30,40,'Game')), \
            patch('native_live.service.preflight',return_value={'stop_reason':'preflight_complete'}) as preflight:
            self.assertEqual(native_preflight.main(['--output-dir',tmp]),0)
        self.assertEqual(preflight.call_args.args,(40,Path(tmp)))
        self.assertEqual(preflight.call_args.kwargs.get('hwnd'),30)
    def test_explicit_pid_does_not_silently_pick_a_different_process(self):
        with tempfile.TemporaryDirectory() as tmp,patch('window_target.resolve_target') as resolve, \
            patch('native_live.service.preflight',return_value={'stop_reason':'preflight_complete'}) as preflight:
            native_preflight.main(['--pid','40','--output-dir',tmp])
        resolve.assert_not_called()
        self.assertEqual(preflight.call_args.args[0],40)
    def test_explicit_window_target_can_be_passed_for_selected_process(self):
        with tempfile.TemporaryDirectory() as tmp,patch('window_target.resolve_target') as resolve, \
            patch('native_live.service.preflight',return_value={'stop_reason':'preflight_complete'}) as preflight:
            native_preflight.main(['--pid','40','--hwnd','30','--output-dir',tmp])
        resolve.assert_not_called();self.assertEqual(preflight.call_args.kwargs['hwnd'],30)

    def test_korean_locator_keeps_its_handle_with_taiwan_running(self):
        windows=[WindowTarget(30,40,'瑪奇 Mobile','MabinogiMobile.exe'),
                 WindowTarget(50,60,'마비노기 모바일','MabinogiMobile.exe')]
        result={'stop_reason':'preflight_complete','build_adapter':{'adapter_id':'kr-20261012-research-candidate'}}
        with tempfile.TemporaryDirectory() as tmp,patch('window_target.list_windows',return_value=windows),\
            patch('native_live.service.preflight',return_value=result) as preflight:
            self.assertEqual(native_preflight.main(['--korean','--output-dir',tmp]),0)
        self.assertEqual(preflight.call_args.args,(60,Path(tmp)))
        self.assertEqual(preflight.call_args.kwargs['hwnd'],50)

    def test_korean_preflight_does_not_accept_taiwan_hash_under_korean_title(self):
        result={'stop_reason':'preflight_complete','build_adapter':{'adapter_id':'unity-static-v1'}}
        with tempfile.TemporaryDirectory() as tmp,patch('window_target.list_windows',return_value=[WindowTarget(50,60,'마비노기 모바일','MabinogiMobile.exe')]),\
            patch('native_live.service.preflight',return_value=result):
            self.assertEqual(native_preflight.main(['--korean','--output-dir',tmp]),1)
            import json
            saved=json.loads((Path(tmp)/'native-preflight.json').read_text())
            self.assertEqual(saved['unavailable_reason'],'game_build')


if __name__=='__main__':unittest.main()
