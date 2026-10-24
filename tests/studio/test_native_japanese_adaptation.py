"""JP uses its own fingerprints and explicit test entry, never Korean offsets."""
import tempfile,threading,unittest
from pathlib import Path
from types import SimpleNamespace
from dataclasses import replace
from unittest.mock import Mock,patch
from native_live import build_adapters as registry
from native_live import native_provider_backend as provider

HASHES=dict(gameassembly='214a60312b572a5ca55514f8a4ed51459559c97d2527028afb596aadf7b428a4',
    metadata='ff5bd8ef32c53d05322e2f961b3e05667c7350bcbf7bd7a466d83468123666bb',
    unityplayer=registry.UNITY_BUILD)

class JapaneseAdapterTests(unittest.TestCase):
    def test_exact_japanese_build_has_separate_slots_and_no_default_input(self):
        adapter=registry.select_adapter(HASHES)
        self.assertEqual(adapter.palette_class_rva,0x10909e58)
        self.assertEqual(adapter.palette_uninitialized_marker,0x20035ba5)
        self.assertEqual(adapter.input_class_rva,0x10959120)
        self.assertEqual(adapter.input_class_uninitialized_marker,0x20042105)
        self.assertEqual(adapter.mouse_getter_cache_rva,0x11308df8)
        self.assertFalse(adapter.input_verified)
        self.assertFalse(registry.input_is_allowed(SimpleNamespace(adapter=adapter)))
        for key in HASHES:
            with self.subTest(key=key),self.assertRaises(registry.BuildUnsupported):
                registry.select_adapter(dict(HASHES,**{key:'0'*64}))

    def test_japanese_marker_does_not_scan_uninitialized_palette(self):
        b=provider.CurrentBuildBackend.__new__(provider.CurrentBuildBackend)
        b.adapter=registry.select_adapter(HASHES);b.base=0x100000000;b.clock=lambda:1.
        addresses=[]
        def read(address):addresses.append(address);return 0x20035ba5
        b.reader=SimpleNamespace(u64=read,guard=lambda:None,regions=Mock(side_effect=AssertionError('No heap scan')))
        b.process_identity=lambda:(1,2,b.base,HASHES['gameassembly'])
        self.assertIsNone(b.discover(10.,lambda:None))
        self.assertEqual(addresses,[b.base+0x10909e58]*2)
        self.assertTrue(b.last_discovery_diagnostic['initial_absence_verified'])

    def test_explicit_validation_is_bound_to_registered_server(self):
        adapter=registry.select_adapter(HASHES)
        b=SimpleNamespace(adapter=adapter)
        registry.enable_known_validation_input(b,adapter.adapter_id)
        self.assertTrue(registry.input_is_allowed(b));self.assertFalse(adapter.input_verified)
        for wrong in (registry.KR_ADAPTER,replace(adapter,palette_class_rva=0x1000),None):
            with self.subTest(adapter=wrong),self.assertRaises(ValueError):
                registry.enable_known_validation_input(SimpleNamespace(adapter=wrong),adapter.adapter_id)

    def test_japanese_launch_uses_japanese_adapter_and_rejects_korean_launch(self):
        from native_live import service
        from window_target import WindowTarget
        adapter=registry.select_adapter(HASHES)
        for flag,allowed in (('--validate-japanese-build',True),('--validate-korean-build',False)):
            with self.subTest(flag=flag),tempfile.TemporaryDirectory() as folder:
                owner=SimpleNamespace(folder=Path(folder),stop=threading.Event(),event=Mock())
                b=SimpleNamespace(adapter=adapter,close=Mock())
                with patch.object(service.sys,'argv',['ColorStudio.exe',flag]), \
                    patch.object(service,'resolve_target',return_value=WindowTarget(1,2,'マビモバ','MabinogiMobile.exe')), \
                    patch.object(service,'_prepare',return_value=(b,{})), \
                    patch.object(service,'collect_validation_session',return_value={'stop_reason':'no_active_palette_timeout'}) as collect:
                    r=service.run_native_search(owner,[dict(enabled=True,exact=True,colors=['#FFFFFF'],tolerance=8)]*3)
                self.assertEqual(bool(collect.call_count),allowed)
                self.assertEqual(r['actual_input_attempts'],0)
                self.assertFalse(r['build_adapter']['input_verified'] if 'build_adapter' in r else False)

if __name__=='__main__':unittest.main()
