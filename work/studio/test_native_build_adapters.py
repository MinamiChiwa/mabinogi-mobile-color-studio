import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

class BuildAdapterTests(unittest.TestCase):
    def test_unknown_build_records_fingerprint_without_constructing_input(self):
        from native_live.build_adapters import BuildUnsupported,select_adapter
        from native_live import service
        hashes={'gameassembly':'a'*64,'metadata':'b'*64,'unityplayer':'c'*64}
        with self.assertRaises(BuildUnsupported) as raised:select_adapter(hashes)
        with tempfile.TemporaryDirectory() as folder,patch.object(service,'configure_ocr'),\
                patch.object(service,'prepare_timer_assets',return_value={}),patch.object(service,'prepare_hex_assets',return_value={}),\
                patch.object(service,'CurrentBuildBackend',side_effect=raised.exception),patch.object(service,'ProjectClosedLoopIO') as sender:
            result=service.preflight(123,folder,hwnd=20)
            diagnostic=json.loads((Path(folder)/'native-preparation.json').read_text(encoding='utf-8'))
        self.assertEqual(result['unavailable_reason'],'game_build');sender.assert_not_called()
        self.assertEqual(diagnostic['build_diagnostic']['hashes'],hashes)
        self.assertEqual(diagnostic['inputs_sent'],0)

    def test_known_build_is_selected_by_fingerprint_independent_of_server_title(self):
        from native_live.build_adapters import select_adapter,TW_BUILD,TW_METADATA
        adapter=select_adapter(dict(gameassembly=TW_BUILD,metadata=TW_METADATA,unityplayer='c'*64))
        self.assertEqual(adapter.palette_class_rva,0x106c9010)
