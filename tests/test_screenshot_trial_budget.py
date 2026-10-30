"""A multi-gesture colour trial cannot consume its measured return allowance."""
from types import SimpleNamespace

import numpy as np
import pytest

from screenshot_control import Budget,Controller,TimeEnded


def test_each_trial_gesture_leaves_readback_and_return_time_without_blocking_recovery(monkeypatch):
    import screenshot_control as m
    now=[85.];monkeypatch.setattr(m.time,'monotonic',lambda:now[0])
    monkeypatch.setattr(m.time,'sleep',lambda seconds:None)
    c=object.__new__(Controller);c.budget=Budget(100,None,now=0.)
    for name,values in dict(capture=[.1,2.],registration=[.1,2.],verify=[.1,1.]).items():
        for value in values:c.budget.record_cost(name,value)
    c.refinement_anchor=dict(matrix=np.eye(3));c._motion_return_target=None
    c.check=lambda:None;c.owner=SimpleNamespace(consume_retry_request=lambda:False)
    c.return_cost=lambda *a,**kw:4.
    c.frame=np.zeros((2,2,3));c.pose=np.eye(3);c.pose_known=True;c.actions=[]
    c.scene=SimpleNamespace(board=(0,0,100,100))
    c.game=SimpleNamespace(release=lambda:None,move_to=lambda point:None)
    c.capture=lambda label:c.frame;c.register=lambda *a:(np.eye(3),{})
    c.record_motion=lambda *a:None;c.write=lambda *a:None
    performed=[]
    def trial():performed.append('trial');now[0]+=4.
    c.act('trial',trial,receipt={})
    with pytest.raises(TimeEnded):c.act('trial-2',trial,receipt={})
    assert performed==['trial'] and not c.input_in_progress
    c.budget.recovering=True
    c.act('return',lambda:performed.append('return'),receipt={})
    assert performed==['trial','return']
    now[0]=96.
    with pytest.raises(TimeEnded):c.act('too-late-return',lambda:performed.append('late'),receipt={})
    assert performed==['trial','return']


def test_mid_move_timeout_clears_trial_scope_for_return():
    c=object.__new__(Controller);c.budget=SimpleNamespace(recovering=False)
    c.best=dict(matrix=np.eye(3))
    def expire(*a):raise TimeEnded()
    c._move_to=expire
    with pytest.raises(TimeEnded):c.move_to(np.eye(3),local=True)
    assert c._motion_return_target is None and c._motion_destination is None
