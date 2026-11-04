"""Completed diagnostic runs retain the latest ten, regardless of age."""
import os

import pytest

from session_store import ACTIVE_MARKER, cleanup_sessions, mark_session


def make_session(root, index, stamp, active=False):
    folder=root/f'20261001-1200{index:02d}'
    mark_session(folder)
    (folder/'run-summary.json').write_text('{}')
    if active:
        (folder/ACTIVE_MARKER).write_text('active')
    for path in folder.iterdir():
        os.utime(path,(stamp,stamp))
    os.utime(folder,(stamp,stamp))
    return folder


@pytest.mark.parametrize('age_days',[1,60])
def test_only_latest_ten_completed_runs_survive_regardless_of_age(tmp_path,age_days):
    now=1800000000.
    folders=[make_session(tmp_path,i,now-age_days*86400+i) for i in range(12)]
    unknown=tmp_path/'20261001-120059'
    unknown.mkdir()
    (unknown/'user.txt').write_text('keep')
    assert cleanup_sessions(tmp_path,now=now)['removed']==2
    assert all(not folder.exists() for folder in folders[:2])
    assert all(folder.exists() for folder in folders[2:])
    assert (unknown/'user.txt').read_text()=='keep'


def test_four_case_run_survives_without_age_expiration(tmp_path):
    now=1800000000.
    folders=[make_session(tmp_path,i,now-(50-i)*86400) for i in range(4)]
    assert cleanup_sessions(tmp_path,now=now)['removed']==0
    assert all(folder.exists() for folder in folders)


def test_recent_and_active_writes_are_protected_until_stale(tmp_path):
    now=1800000000.
    completed=[make_session(tmp_path,i,now-86400+i) for i in range(10)]
    active=make_session(tmp_path,10,now-2*86400,active=True)
    os.utime(active/ACTIVE_MARKER,(now-60,now-60))
    recent=make_session(tmp_path,11,now-3*86400)
    os.utime(recent/'run-summary.json',(now-30,now-30))
    assert cleanup_sessions(tmp_path,now=now)['removed']==1
    assert active.exists() and recent.exists()
    assert not completed[0].exists()
    assert all(folder.exists() for folder in completed[1:])
    assert cleanup_sessions(tmp_path,now=now+600)['removed']==1
    assert not active.exists()
    assert not completed[0].exists()
    assert recent.exists()
    assert all(folder.exists() for folder in completed[1:])
