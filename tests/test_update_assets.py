"""Release assets: signed manifest plus blobs only, verified against the package."""
import os

import pytest

from scripts.build_update_assets import build_assets
from scripts.verify_update_assets import verify_assets
from signing import KEYS, SEED


@pytest.fixture
def package(tmp_path):
    root = tmp_path / 'ColorStudio'
    (root / '_internal' / 'qt_ui' / 'qml').mkdir(parents=True)
    (root / 'ColorStudio.exe').write_bytes(os.urandom(70000))
    (root / '_internal' / 'core.dll').write_bytes(os.urandom(90000))
    (root / '_internal' / 'qt_ui' / 'qml' / 'Main.qml').write_text('import QtQuick\n', encoding='utf-8')
    (root / 'README.md').write_text('# guide\n', encoding='utf-8')
    return root


def build(package, out, **kw):
    return build_assets(package, out, kw.pop('version', '0.5.0'), 'stable', SEED,
                        key_id='test', release_sequence=kw.pop('sequence', 3), **kw)


def test_assets_are_manifest_signature_and_blobs_only(package, tmp_path):
    out = tmp_path / 'assets'
    result = build(package, out)
    names = {p.name for p in out.iterdir()}
    assert {'update-manifest.json', 'update-manifest.sig'} <= names
    assert names - {'update-manifest.json', 'update-manifest.sig'} == set(result['blobs'])
    assert not any(name.startswith('UPDATE-ONLY') for name in names)
    assert verify_assets(out, package, trusted_keys=KEYS)['files'] == 4


def test_tampered_blob_fails_verification(package, tmp_path):
    out = tmp_path / 'assets'
    result = build(package, out)
    blob = out / result['blobs'][0]
    data = bytearray(blob.read_bytes())
    data[len(data) // 2] ^= 0xFF
    blob.write_bytes(bytes(data))
    with pytest.raises(ValueError, match='Blob hash'):
        verify_assets(out, package, trusted_keys=KEYS)


def test_previous_manifest_reports_only_changed_download(package, tmp_path):
    first = tmp_path / 'first'
    build(package, first)
    (package / 'ColorStudio.exe').write_bytes(os.urandom(70000))
    second = build(package, tmp_path / 'second', version='0.5.1', sequence=4,
                   previous_manifest=first / 'update-manifest.json')
    assert 0 < second['changed_bytes'] < second['download_bytes']
