import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

class BuildAdapterTests(unittest.TestCase):
    def new_korean_adapter(self):
        from native_live.build_adapters import select_adapter
        return select_adapter(dict(gameassembly='6bd11b074630ffd718301ba7ccb65af9c4505b6034aea0b1f6b2004b86f3f409',
            metadata='3fa44401ae69c9e782081e10eab7ce5f7e156e2ec5a86dc42847084550f0939c',
            unityplayer='e969642866c2195f16a0bd0e52ff8ffe87cad5b213fda9a62ca1564970e2fa26'))

    def test_new_korean_uninitialized_palette_repeats_only_new_slot(self):
        from native_live.native_provider_backend import CurrentBuildBackend
        from types import SimpleNamespace
        from unittest.mock import Mock
        backend=CurrentBuildBackend.__new__(CurrentBuildBackend)
        backend.adapter=self.new_korean_adapter();backend.base=0x100000000;backend.clock=lambda:1.
        addresses=[]
        def read(address):addresses.append(address);return 0x20038007
        backend.reader=SimpleNamespace(u64=read,guard=lambda:None,regions=Mock(side_effect=AssertionError('No heap scan')))
        backend.process_identity=lambda:(1,2,backend.base,backend.adapter.gameassembly_sha256)
        self.assertIsNone(backend.discover(10.,lambda:None))
        self.assertEqual(addresses,[backend.base+0x1117f2e8]*2)
        self.assertTrue(backend.last_discovery_diagnostic['initial_absence_verified'])

    def test_new_korean_input_branch_reads_new_slots_and_keeps_runtime_guard(self):
        from native_live.read_dye_input_backend import read_input_backend
        from types import SimpleNamespace
        import struct
        base=0x100000000;unity=0x200000000;cls=0x300000000;static=cls+0x1000
        manager=cls+0x2000;manager_cls=cls+0x3000;screen=cls+0x4000
        memory={base+0x1121ebd0:struct.pack('<Q',cls),cls+0xb8:struct.pack('<Q',static),
            static:struct.pack('<Q',manager),manager:struct.pack('<Q',manager_cls),
            manager+0x18:struct.pack('<Q',0),base+0x11d68be0:struct.pack('<Q',unity+0x185310),
            unity+0x1b23390:struct.pack('<Q',screen),screen+0x120:struct.pack('<4i2f',0,0,0,0,1.,1.)}
        reads=[]
        def read(address,size):reads.append(address);return memory[address][:size]
        reader=SimpleNamespace(guard=lambda:None,read=read,
            class_name=lambda c:'MM.Client.Framework.InputSystem.MMInputSystem' if c==cls else 'MM.Client.Framework.InputSystem.InputManager',
            fields=lambda c:{'inputSystem':0} if c==cls else {'inputEventAssistant':0x18})
        backend=SimpleNamespace(reader=reader,base=base,unityplayer_base=unity,adapter=self.new_korean_adapter(),
            unityplayer_version='e969642866c2195f16a0bd0e52ff8ffe87cad5b213fda9a62ca1564970e2fa26',
            process_identity=lambda:(1,2,base,'new-kr'))
        record=read_input_backend(backend,10.,clock=lambda:1.)
        self.assertEqual(record['inputs_sent'],0)
        self.assertEqual(reads.count(base+0x1121ebd0),2)
        self.assertEqual(reads.count(base+0x11d68be0),2)
        memory[manager+0x18]=struct.pack('<Q',cls)
        with self.assertRaisesRegex(ValueError,'assistant'):read_input_backend(backend,10.,clock=lambda:1.)

    def test_readonly_korean_preflight_accepts_new_family_without_allowing_japanese(self):
        import native_preflight
        from native_live.build_adapters import JP_ADAPTER
        for adapter,want in ((self.new_korean_adapter(),0),(JP_ADAPTER,1)):
            with tempfile.TemporaryDirectory() as folder,patch('native_live.service.preflight',
                    return_value=dict(stop_reason='preflight_complete',build_adapter=adapter.diagnostic())):
                self.assertEqual(native_preflight.main(['--pid','123','--korean','--output-dir',folder]),want)

    def test_updated_korean_files_select_new_entries_without_losing_old_build(self):
        from native_live.build_adapters import select_adapter,KR_ADAPTER
        hashes=dict(gameassembly='6bd11b074630ffd718301ba7ccb65af9c4505b6034aea0b1f6b2004b86f3f409',
            metadata='3fa44401ae69c9e782081e10eab7ce5f7e156e2ec5a86dc42847084550f0939c',
            unityplayer='e969642866c2195f16a0bd0e52ff8ffe87cad5b213fda9a62ca1564970e2fa26')
        new=select_adapter(hashes)
        self.assertEqual((new.palette_class_rva,new.palette_uninitialized_marker),(0x1117f2e8,0x20038007))
        self.assertEqual((new.input_class_rva,new.input_class_uninitialized_marker),(0x1121ebd0,0x20044b51))
        self.assertEqual(new.mouse_getter_cache_rva,0x11d68be0)
        self.assertFalse(new.input_verified)
        self.assertIs(select_adapter(dict(gameassembly=KR_ADAPTER.gameassembly_sha256,
            metadata=KR_ADAPTER.metadata_sha256,unityplayer=hashes['unityplayer'])),KR_ADAPTER)

    def test_selected_korean_server_accepts_both_exact_builds_and_rejects_modified_layout(self):
        from native_live.build_adapters import select_adapter,KR_ADAPTER,enable_selected_server_input,input_is_allowed
        from dataclasses import replace
        from types import SimpleNamespace
        new=select_adapter(dict(gameassembly='6bd11b074630ffd718301ba7ccb65af9c4505b6034aea0b1f6b2004b86f3f409',
            metadata='3fa44401ae69c9e782081e10eab7ce5f7e156e2ec5a86dc42847084550f0939c',
            unityplayer='e969642866c2195f16a0bd0e52ff8ffe87cad5b213fda9a62ca1564970e2fa26'))
        for adapter in (new,KR_ADAPTER):
            backend=SimpleNamespace(adapter=adapter)
            self.assertFalse(input_is_allowed(backend))
            enable_selected_server_input(backend,'kr')
            self.assertTrue(input_is_allowed(backend))
        for server,adapter in (('jp',new),('tw',new),('kr',replace(new,palette_class_rva=0x1000))):
            backend=SimpleNamespace(adapter=adapter)
            with self.assertRaises(ValueError):enable_selected_server_input(backend,server)
            self.assertFalse(input_is_allowed(backend))

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
        from native_live.build_adapters import select_adapter,TW_BUILD,TW_METADATA,UNITY_BUILD
        adapter=select_adapter(dict(gameassembly=TW_BUILD,metadata=TW_METADATA,unityplayer=UNITY_BUILD))
        self.assertEqual(adapter.palette_class_rva,0x106c9010)
