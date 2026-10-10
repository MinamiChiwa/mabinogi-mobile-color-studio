"""Portable failures must retain the failed layer and physical measurements."""
import copy,json,tempfile,threading,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock,patch
from native_live import service
from native_status import result_text
from window_target import WindowTarget


class NativePortableDiagnosticsTests(unittest.TestCase):
    def test_preflight_failure_saves_actual_paths_and_window_stage(self):
        backend=MagicMock()
        backend.build_files=dict(gameassembly=Path('D:/游戏/appdata/GameAssembly.dll'),
            unityplayer=Path('D:/游戏/appdata/UnityPlayer.dll'),metadata=Path('D:/游戏/appdata/Metadata.dat'))
        backend.version='game-hash';backend.metadata_version='metadata-hash';backend.unityplayer_version='unity-hash'
        backend.observe_window_context.side_effect=ValueError('Bound game window/Unity extents differ')
        backend.last_window_diagnostic=dict(window=dict(client_size_physical=[1920,1440],dpi=144),
            unity_screen=dict(size=[1280,960]),extent_one_to_one=False)
        with tempfile.TemporaryDirectory() as tmp,patch.object(service,'CurrentBuildBackend',return_value=backend), \
            patch.object(service,'configure_ocr'),patch.object(service,'prepare_timer_assets',return_value={}), \
            patch.object(service,'prepare_hex_assets',return_value={}):
            result=service.preflight(1,Path(tmp))
            diagnostic=json.loads((Path(tmp)/'native-preparation.json').read_text(encoding='utf8'))
        self.assertEqual(diagnostic['stage'],'window_context')
        self.assertEqual(diagnostic['build_files']['unityplayer'],'D:\\游戏\\appdata\\UnityPlayer.dll')
        self.assertEqual(diagnostic['window_context']['window']['client_size_physical'],[1920,1440])
        self.assertEqual(result['unavailable_reason'],'coordinate_mapping')
        backend.close.assert_called_once()

    def test_module_failure_is_not_presented_as_a_window_failure(self):
        owner=SimpleNamespace(folder=None,stop=threading.Event(),event=lambda *a,**k:None)
        with tempfile.TemporaryDirectory() as tmp,patch.object(service,'resolve_target',return_value=WindowTarget(1,2,'Game')), \
            patch.object(service,'_prepare',side_effect=ValueError('Expected unique current-build UnityPlayer module')):
            owner.folder=Path(tmp)
            result=service.run_native_search(owner,[dict(enabled=True,exact=True,colors=['#000000'],tolerance=0.)]*3)
        self.assertEqual(result['unavailable_reason'],'module_resolution')
        title,body=result_text(result)
        self.assertIn('游戏模块',title);self.assertNotIn('窗口条件不支持',title)

    def test_build_mismatch_remains_a_build_error(self):
        title,body=result_text(dict(stop_reason='unavailable',verified=False,unavailable_reason='game_build'))
        self.assertIn('游戏版本',title)
        self.assertNotIn('分辨率',body)


if __name__=='__main__':unittest.main()
