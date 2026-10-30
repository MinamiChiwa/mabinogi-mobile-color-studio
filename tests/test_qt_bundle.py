"""Keep build-machine PATH libraries from breaking the portable Qt runtime."""
from types import SimpleNamespace

import pytest

from qt_bundle import prefer_system_icu


@pytest.mark.parametrize('bundled_ok,system_ok', [(False, True), (True, True), (False, False)])
def test_icu_export_contract(tmp_path, monkeypatch, bundled_ok, system_ok):
    internal, system = tmp_path / 'internal', tmp_path / 'system'
    internal.mkdir();system.mkdir()
    for path in (internal / 'Qt6Core.dll', internal / 'icuuc.dll', system / 'icuuc.dll'):
        path.touch()
    class PE:
        def __init__(self, path, **kwargs):
            self.path = path
            self.DIRECTORY_ENTRY_IMPORT = []
            if path.endswith('Qt6Core.dll'):
                self.DIRECTORY_ENTRY_IMPORT = [SimpleNamespace(dll=b'icuuc.dll', imports=[SimpleNamespace(name=b'ucnv_open')])]
            valid = system_ok if path == str(system / 'icuuc.dll') else bundled_ok
            self.DIRECTORY_ENTRY_EXPORT = SimpleNamespace(symbols=[SimpleNamespace(name=b'ucnv_open' if valid else b'ucnv_open_78')])
        def parse_data_directories(self, **kwargs):
            pass
        def close(self):
            pass
    monkeypatch.setattr('pefile.PE', PE)
    if not bundled_ok and not system_ok:
        with pytest.raises(RuntimeError, match='no compatible system'):
            prefer_system_icu(internal, system)
        assert (internal / 'icuuc.dll').exists()
    else:
        assert prefer_system_icu(internal, system) == ([] if bundled_ok else ['icuuc.dll'])
        assert (internal / 'icuuc.dll').exists() == bundled_ok
