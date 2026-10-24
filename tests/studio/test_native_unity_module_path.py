"""Loaded module paths, rather than a machine-specific install, select Unity."""
import ctypes
import importlib
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


class _ModuleAPI:
    """Controlled PSAPI boundary: no live process inspection in these tests."""
    def __init__(self, paths):
        self.paths = dict(paths)

    def EnumProcessModulesEx(self, handle, modules, capacity, needed, flags):
        if handle != 17 or flags != 3:
            raise AssertionError('Unexpected module enumeration target')
        needed._obj.value = len(self.paths) * ctypes.sizeof(ctypes.c_void_p)
        if needed._obj.value <= capacity:
            for index, base in enumerate(self.paths):
                modules[index] = base
        return True

    def GetModuleFileNameExW(self, handle, module, name, capacity):
        if handle != 17 or capacity < len(self.paths[module]) + 1:
            raise AssertionError('Unexpected module path request')
        name.value = self.paths[module]
        return len(name.value)


class NativeUnityModulePathTests(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module('native_live.read_unity_screen')

    def resolve(self, paths, *, module_files=None, **kwargs):
        reader = SimpleNamespace(h=17)
        if module_files is not None:
            reader.module_files = module_files
        with patch.object(self.module, 'P', _ModuleAPI(paths)):
            return self.module.unityplayer_module_base(reader, **kwargs)

    def test_unique_loaded_unityplayer_is_found_in_portable_installations(self):
        for unity in (
            r'C:\Nexon\Library\MabinogiMobile_TW\appdata\UnityPlayer.dll',
            r'D:\Games\MabinogiMobile_TW\appdata\UnityPlayer.dll',
            r'E:\遊戲\瑪奇行動版\appdata\uNiTyPlAyEr.DlL',
            'D:/Games/MabinogiMobile_TW/appdata/UnityPlayer.dll',
            r'\\?\D:\Games\MabinogiMobile_TW\appdata\UnityPlayer.dll',
        ):
            with self.subTest(unity=unity):
                self.assertEqual(self.resolve({0x10000: r'C:\Windows\System32\kernel32.dll',
                                              0x20000: unity}), 0x20000)

    def test_selected_process_path_controls_unity_module_selection(self):
        self.assertEqual(self.resolve(
            {0x10000: r'C:\Nexon\Library\MabinogiMobile_TW\appdata\UnityPlayer.dll',
             0x20000: r'D:\Games\current\UnityPlayer.dll'},
            module_files={'unityplayer.dll': r'D:\Games\current\UnityPlayer.dll'}), 0x20000)

    def test_selected_path_compares_windows_case_slashes_and_extended_prefix(self):
        cases = (
            (r'\\?\D:\遊戲\APPDATA\UnityPlayer.dll', 'd:/遊戲/appdata/unityplayer.DLL'),
            (r'\\?\UNC\Server\遊戲\UnityPlayer.dll', r'\\server\遊戲\unityplayer.dll'),
        )
        for loaded, expected in cases:
            with self.subTest(loaded=loaded):
                self.assertEqual(self.resolve({0x20000: loaded},
                    module_files={'unityplayer.dll': expected}), 0x20000)

    def test_verified_build_path_overrides_reader_path(self):
        self.assertEqual(self.resolve(
            {0x10000: r'C:\Nexon\Library\MabinogiMobile_TW\appdata\UnityPlayer.dll',
             0x20000: r'D:\Games\current\UnityPlayer.dll'},
            module_files={'unityplayer.dll': r'C:\Nexon\Library\MabinogiMobile_TW\appdata\UnityPlayer.dll'},
            expected_path=Path(r'D:\Games\current\UnityPlayer.dll')), 0x20000)

    def test_non_unity_verified_build_path_is_rejected(self):
        with self.assertRaises(ValueError):
            self.resolve({0x20000: r'D:\Games\current\GameAssembly.dll'},
                         expected_path=r'D:\Games\current\GameAssembly.dll')

    def test_missing_or_lookalike_unity_module_is_rejected(self):
        for paths in ({}, {0x10000: r'D:\Games\FakeUnityPlayer.dll'},
                      {0x10000: r'D:\Games\UnityPlayer.dll.backup'}):
            with self.subTest(paths=paths), self.assertRaises(ValueError):
                self.resolve(paths)

    def test_multiple_unbound_unity_modules_are_rejected(self):
        with self.assertRaises(ValueError):
            self.resolve({0x10000: r'C:\Nexon\Library\MabinogiMobile_TW\appdata\UnityPlayer.dll',
                          0x20000: r'D:\Other\UnityPlayer.dll'})

    def test_selected_path_mismatch_is_rejected(self):
        with self.assertRaises(ValueError):
            self.resolve({0x10000: r'C:\Nexon\Library\MabinogiMobile_TW\appdata\UnityPlayer.dll'},
                         module_files={'unityplayer.dll': r'D:\Games\UnityPlayer.dll'})

    def test_distinct_unicode_directories_cannot_match_verified_build_path(self):
        with self.assertRaises(ValueError):
            self.resolve({0x20000: r'D:\Strasse\UnityPlayer.dll'},
                         expected_path=r'D:\Straße\UnityPlayer.dll')

    def test_loaded_file_alias_matches_canonical_verified_build_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);verified=root/'verified'/'UnityPlayer.dll';loaded=root/'alias'/'UnityPlayer.dll'
            verified.parent.mkdir();loaded.parent.mkdir()
            verified.write_bytes(b'verified Unity build')
            os.link(verified,loaded)
            self.assertEqual(self.resolve({0x20000: str(loaded)},
                expected_path=verified.resolve()),0x20000)

    def test_distinct_existing_dll_cannot_match_verified_build_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);verified=root/'verified'/'UnityPlayer.dll';loaded=root/'other'/'UnityPlayer.dll'
            verified.parent.mkdir();loaded.parent.mkdir()
            verified.write_bytes(b'verified Unity build');loaded.write_bytes(b'other Unity build')
            with self.assertRaises(ValueError):
                self.resolve({0x20000: str(loaded)},expected_path=verified.resolve())

    def test_duplicate_modules_at_selected_path_are_rejected(self):
        unity = r'C:\Nexon\Library\MabinogiMobile_TW\appdata\UnityPlayer.dll'
        with self.assertRaises(ValueError):
            self.resolve({0x10000: unity, 0x20000: unity},
                         module_files={'unityplayer.dll': unity})


if __name__ == '__main__':
    unittest.main()
