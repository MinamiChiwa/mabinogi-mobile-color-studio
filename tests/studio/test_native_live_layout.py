"""Process module paths own build selection; no fixed machine installation."""
import importlib,importlib.util,tempfile,unittest
from pathlib import Path


class NativeLiveLayoutTests(unittest.TestCase):
    def test_selected_process_paths_resolve_metadata_and_output_independently(self):
        self.assertIsNotNone(importlib.util.find_spec('native_live.build_layout'),'Portable build resolver missing')
        module=importlib.import_module('native_live.build_layout')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'different-install';metadata=root/'MabinogiMobile_Data/il2cpp_data/Metadata/global-metadata.dat'
            metadata.parent.mkdir(parents=True);metadata.write_bytes(b'metadata')
            for name in ('GameAssembly.dll','UnityPlayer.dll'):(root/name).write_bytes(b'build')
            result=module.resolve_build_files({'gameassembly.dll':str(root/'GameAssembly.dll'),
                'unityplayer.dll':str(root/'UnityPlayer.dll')})
            self.assertEqual(result['metadata'],metadata.resolve())
            self.assertEqual(result['gameassembly'],(root/'GameAssembly.dll').resolve())
    def test_missing_or_split_module_installation_is_rejected(self):
        self.assertIsNotNone(importlib.util.find_spec('native_live.build_layout'))
        from native_live.build_layout import resolve_build_files
        for paths in ({},{'gameassembly.dll':'C:/missing.dll'},
            {'gameassembly.dll':'C:/a/GameAssembly.dll','unityplayer.dll':'C:/b/UnityPlayer.dll'}):
            with self.assertRaises((ValueError,OSError)):resolve_build_files(paths)


if __name__=='__main__':unittest.main()
