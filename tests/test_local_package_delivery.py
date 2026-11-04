"""Local package replacement preserves player records and removes owned old bytes."""
from zipfile import ZipFile

import pytest

from scripts.build_local_package import deliver


def candidate(root,name,content):
    folder=root/name/'ColorStudio'
    (folder/'_internal').mkdir(parents=True)
    (folder/'ColorStudio.exe').write_bytes(content)
    (folder/'_internal/library.dll').write_bytes(b'dependency')
    return folder


def test_replacement_keeps_only_latest_zip_and_preserves_records(tmp_path):
    first=candidate(tmp_path,'build-one',b'old')
    old=deliver(tmp_path,first,'0.5.0',tmp_path/'evidence/one')
    app=tmp_path/'发布包/ColorStudio'
    (app/'data').mkdir()
    (app/'data/history.json').write_text('player records')
    (app/'personal-note.txt').write_text('keep me')
    second=candidate(tmp_path,'build-two',b'new')
    new=deliver(tmp_path,second,'0.5.1',tmp_path/'evidence/two')
    assert not old.exists() and new.exists()
    assert (app/'ColorStudio.exe').read_bytes()==b'new'
    assert (app/'data/history.json').read_text()=='player records'
    preserved=tmp_path/'runtime/local-package-records/two'
    assert (preserved/'personal-note.txt').read_text()=='keep me'
    assert not (preserved/'ColorStudio.exe').exists()
    with ZipFile(new) as archive:
        assert 'ColorStudio/ColorStudio.exe' in archive.namelist()
        assert not any('/data/' in name for name in archive.namelist())


def test_unmanaged_archive_collision_leaves_existing_program_untouched(tmp_path):
    deliver(tmp_path,candidate(tmp_path,'one',b'old'),'0.5.0',tmp_path/'evidence/one')
    collision=tmp_path/'发布包/ColorStudio-v0.5.1-Windows-x64.zip'
    collision.write_bytes(b'user file')
    prepared=candidate(tmp_path,'two',b'new')
    with pytest.raises(ValueError,match='unmanaged or modified'):
        deliver(tmp_path,prepared,'0.5.1',tmp_path/'evidence/two')
    assert (tmp_path/'发布包/ColorStudio/ColorStudio.exe').read_bytes()==b'old'
    assert collision.read_bytes()==b'user file'
    assert prepared.exists()


def test_modified_packaged_file_is_preserved(tmp_path):
    deliver(tmp_path,candidate(tmp_path,'one',b'old'),'0.5.0',tmp_path/'evidence/one')
    (tmp_path/'发布包/ColorStudio/_internal/library.dll').write_bytes(b'edited')
    deliver(tmp_path,candidate(tmp_path,'two',b'new'),'0.5.0',tmp_path/'evidence/two')
    assert (tmp_path/'runtime/local-package-records/two/_internal/library.dll').read_bytes()==b'edited'
