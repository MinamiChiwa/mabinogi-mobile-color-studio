"""Fingerprint-selected Korean diagnostics never imply live input permission."""
import json,struct,tempfile,threading,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch

from native_live import build_adapters as registry
from native_live import native_provider_backend as provider
from dataclasses import replace

KR_HASHES=dict(gameassembly='bd9d827b7cd342c677c1e93a752f61c2e75a913d08ac9879ce285c852986ca08',
    metadata='cdeed3914cc11325e9771047bdbe4bb0acf1733f16f01783418f753c2a6fde8a',
    unityplayer='e969642866c2195f16a0bd0e52ff8ffe87cad5b213fda9a62ca1564970e2fa26')


class ServerAdapterTests(unittest.TestCase):
    def adapter(self):return registry.select_adapter(KR_HASHES)

    def test_korean_fingerprint_selects_readonly_candidate_and_shared_unity_layout(self):
        adapter=self.adapter()
        self.assertEqual(adapter.palette_class_rva,0x10d1bf18)
        self.assertEqual(adapter.palette_uninitialized_marker,0x20036bfb)
        self.assertEqual(adapter.input_class_rva,0x10d7e580)
        self.assertEqual(adapter.mouse_getter_cache_rva,0x11694ce8)
        self.assertEqual(adapter.capability,'diagnostic_only')
        self.assertFalse(adapter.input_verified)
        self.assertEqual(adapter.unity_layout,registry.select_adapter(dict(gameassembly=registry.TW_BUILD,
            metadata=registry.TW_METADATA,unityplayer=KR_HASHES['unityplayer'])).unity_layout)
        self.assertTrue(adapter.managed_layout_evidence_sha256)

    def test_missing_or_changed_unity_fingerprint_never_reuses_known_managed_build(self):
        for assembly,metadata in ((KR_HASHES['gameassembly'],KR_HASHES['metadata']),
                                  (registry.TW_BUILD,registry.TW_METADATA)):
            for unity in (None,'a'*64):
                with self.subTest(unity=unity,assembly=assembly):
                    with self.assertRaises(registry.BuildUnsupported):
                        registry.select_adapter(dict(gameassembly=assembly,metadata=metadata,unityplayer=unity))

    def test_korean_uninitialized_palette_repeats_its_own_slot_without_heap_scan(self):
        backend=provider.CurrentBuildBackend.__new__(provider.CurrentBuildBackend)
        backend.adapter=self.adapter();backend.base=0x100000000;backend.clock=lambda:1.
        addresses=[]
        def read(address):addresses.append(address);return 0x20036bfb
        backend.reader=SimpleNamespace(u64=read,guard=lambda:None,regions=Mock(side_effect=AssertionError('No scan before initialization')))
        backend.process_identity=lambda:(1,2,backend.base,KR_HASHES['gameassembly'])
        self.assertIsNone(backend.discover(10.,lambda:None))
        self.assertEqual(addresses,[backend.base+0x10d1bf18]*2)
        self.assertTrue(backend.last_discovery_diagnostic['initial_absence_verified'])
        self.assertEqual(backend.last_discovery_diagnostic['class_value'],'0x20036bfb')

    def test_input_branch_reads_korean_slots_but_grants_no_input(self):
        from native_live.read_dye_input_backend import read_input_backend
        base=0x100000000;unity=0x200000000;cls=0x300000000;static=cls+0x1000
        manager=cls+0x2000;manager_cls=cls+0x3000;screen=cls+0x4000
        memory={base+0x10d7e580:struct.pack('<Q',cls),cls+0xb8:struct.pack('<Q',static),
            static:struct.pack('<Q',manager),manager:struct.pack('<Q',manager_cls),
            manager+0x18:struct.pack('<Q',0),base+0x11694ce8:struct.pack('<Q',unity+0x185310),
            unity+0x1b23390:struct.pack('<Q',screen),screen+0x120:struct.pack('<4i2f',0,0,0,0,1.,1.)}
        reads=[]
        def read(address,size):reads.append(address);return memory[address][:size]
        reader=SimpleNamespace(guard=lambda:None,read=read,
            class_name=lambda c:'MM.Client.Framework.InputSystem.MMInputSystem' if c==cls else 'MM.Client.Framework.InputSystem.InputManager',
            fields=lambda c:{'inputSystem':0} if c==cls else {'inputEventAssistant':0x18})
        backend=SimpleNamespace(reader=reader,base=base,unityplayer_base=unity,adapter=self.adapter(),
            unityplayer_version=KR_HASHES['unityplayer'],process_identity=lambda:(1,2,base,KR_HASHES['gameassembly']))
        record=read_input_backend(backend,10.,clock=lambda:1.)
        self.assertEqual(record['viewport_scale'],[1.,1.]);self.assertFalse(record['ready_for_input'])
        self.assertEqual(record['inputs_sent'],0)
        self.assertNotIn(base+0x1074fa20,reads);self.assertNotIn(base+0x11100078,reads)
        self.assertEqual(reads.count(base+0x10d7e580),2)
        self.assertEqual(reads.count(base+0x11694ce8),2)

    def test_service_rejects_candidate_before_discovery_and_input_construction(self):
        from native_live import service
        with tempfile.TemporaryDirectory() as folder:
            owner=SimpleNamespace(folder=Path(folder),stop=threading.Event(),event=Mock())
            backend=SimpleNamespace(adapter=self.adapter(),close=Mock())
            selected=SimpleNamespace(title='마비노기 모바일',pid=10,hwnd=20)
            rules=[dict(enabled=True,exact=True,colors=['#000000'],tolerance=0.) for _ in range(3)]
            with patch.object(service,'resolve_target',return_value=selected),patch.object(service,'_prepare',return_value=(backend,{})),\
                patch.object(service,'collect_validation_session') as discovery,patch.object(service,'ProjectClosedLoopIO') as inputs:
                result=service.run_native_search(owner,rules)
            discovery.assert_not_called();inputs.assert_not_called()
            self.assertEqual(result['stop_reason'],'unavailable')
            self.assertEqual(result['unavailable_reason'],'game_build')
            self.assertEqual(result['actual_input_attempts'],0)
            self.assertEqual(result['build_adapter']['capability'],'diagnostic_only')
            self.assertFalse(result['build_adapter']['input_verified'])

    def test_direct_input_adapter_cannot_bypass_service_capability(self):
        from native_live.project_closed_loop_io import ProjectClosedLoopIO
        backend=SimpleNamespace(adapter=self.adapter())
        with patch('native_live.project_closed_loop_io.prepare_hex_assets'),\
            patch('native_live.project_probe_io.ProjectProbeIO.__init__') as construct:
            with self.assertRaisesRegex(ValueError,'input verification'):ProjectClosedLoopIO(backend,{},'.')
        construct.assert_not_called()

    def test_explicit_korean_validation_reaches_collection_without_claiming_input_verified(self):
        from native_live import service
        with tempfile.TemporaryDirectory() as folder:
            owner=SimpleNamespace(folder=Path(folder),stop=threading.Event(),event=Mock())
            backend=SimpleNamespace(adapter=self.adapter(),close=Mock())
            selected=SimpleNamespace(title='마비노기 모바일',pid=10,hwnd=20)
            rules=[dict(enabled=True,exact=True,colors=['#000000'],tolerance=0.) for _ in range(3)]
            with patch.object(service.sys,'argv',['ColorStudio.exe','--validate-korean-build']),\
                patch.object(service,'resolve_target',return_value=selected),patch.object(service,'_prepare',return_value=(backend,{})),\
                patch.object(service,'collect_validation_session',return_value={'stop_reason':'no_active_palette_timeout'}) as discovery:
                result=service.run_native_search(owner,rules)
            discovery.assert_called_once()
            self.assertEqual(result['stop_reason'],'no_active_palette_timeout')
            self.assertTrue(result['build_adapter']['validation_input_enabled'])
            self.assertFalse(result['build_adapter']['input_verified'])
            self.assertEqual(result['actual_input_attempts'],0)

    def test_validation_cannot_enable_unknown_or_modified_adapter(self):
        from native_live.build_adapters import enable_known_validation_input
        for adapter in (registry.TW_ADAPTER,replace(self.adapter(),palette_class_rva=0x1000),None):
            backend=SimpleNamespace(adapter=adapter)
            with self.assertRaises(ValueError):enable_known_validation_input(backend,registry.KR_ADAPTER.adapter_id)
            self.assertFalse(getattr(backend,'validation_input_enabled',False))

    def test_explicit_validation_sends_through_existing_checked_input_boundary(self):
        import test_native_protected_io as fixture
        from native_live.build_adapters import enable_known_validation_input
        f=fixture.NativeProtectedIOTests();f.setUp();self.addCleanup(f.doCleanups)
        f.backend.adapter=self.adapter();f.game.send=lambda flags:None
        with self.assertRaises(ValueError):f.protected()
        f.assert_no_inputs()
        enable_known_validation_input(f.backend,registry.KR_ADAPTER.adapter_id)
        receipt=f.protected()
        self.assertTrue(receipt['completed']);self.assertTrue(receipt['released'])
        self.assertEqual(f.io.input_attempts,1)
        self.assertFalse(f.backend.adapter.input_verified)

    def test_korean_managed_wrapper_uses_shared_layout_and_keeps_runtime_field_validation(self):
        from native_live.read_toucharea_rect import read_toucharea_rect_cache
        slot=0x300000000;touch=slot+0x1000;rect=slot+0x2000;system=slot+0x3000
        sc=slot+0x4000;tc=slot+0x5000;rc=slot+0x6000
        names={sc:'Client.CodeGenerated.UI.DyeingPaletteSlot',tc:'MM.Client.Framework.UI.Object.UIChildTransform',rc:'UnityEngine.RectTransform'}
        fields={sc:{'<TouchArea>k__BackingField':0x38},tc:{'<Transform>k__BackingField':0x18,'<UISystem>k__BackingField':0x20},rc:{}}
        memory={slot:sc,slot+0x38:touch,slot+0x28:system,touch:tc,touch+0x18:rect,touch+0x20:system,rect:rc}
        reader=SimpleNamespace(read=lambda a,n:struct.pack('<Q',memory[a])[:n],class_name=names.__getitem__,fields=fields.__getitem__)
        with patch('native_live.read_toucharea_rect.read_native_rect_cache',return_value={'native':'same-unity-layout'}):
            result=read_toucharea_rect_cache(reader,slot,gameassembly_sha256=KR_HASHES['gameassembly'],
                metadata_sha256=KR_HASHES['metadata'],unityplayer_sha256=KR_HASHES['unityplayer'],expected_touch_area=touch)
            self.assertEqual(result['binding']['touch_area_address'],touch)
            fields[sc]['<TouchArea>k__BackingField']=0x40
            with self.assertRaisesRegex(ValueError,'field layout'):
                read_toucharea_rect_cache(reader,slot,gameassembly_sha256=KR_HASHES['gameassembly'],
                    metadata_sha256=KR_HASHES['metadata'],unityplayer_sha256=KR_HASHES['unityplayer'])

    def test_independent_scan_uses_adapter_marker_without_scanning_uninitialized_class(self):
        from native_live.scan_live_dye import scan
        addresses=[];base=0x100000000
        def read(address):addresses.append(address);return 0x20036bfb
        reader=SimpleNamespace(base=base,u64=read,regions=Mock(side_effect=AssertionError('No heap scan')))
        hits,saved,size,elapsed=scan(reader,adapter=self.adapter())
        self.assertEqual((hits,saved,size),([],[],0))
        self.assertEqual(addresses,[base+0x10d1bf18])


if __name__=='__main__':unittest.main()
