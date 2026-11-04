"""Bounded screenshot motion, route admission and sampled colour preservation."""
import math
from types import SimpleNamespace

import numpy as np
import pytest

from screenshot_control import Controller,scale_route,scale_work,SCALE_PAIR_BATCH
from screenshot_refinement import prefer_reachable_scale


def controller(*,respond=True,remaining=200):
    c=object.__new__(Controller);c.pose=np.eye(3);c.pose_known=True;c.period=None
    c.scene=SimpleNamespace(board=np.array([0,0,600,600]),markers=np.array([[100,300],[300,300],[500,300]]))
    c.refinement_anchor=None;c.best=None
    c.budget=SimpleNamespace(recovering=False,estimate=lambda name,default=0:default,
        can_input=lambda needed=0:needed+3<remaining)
    c.relocalize=lambda:True;c.progress=lambda *a,**kw:None;c.write=lambda *a:None
    c.commands=[]
    def scale(value):
        if respond:
            delta=np.diag([value,value,1.]);delta[:2,2]=300*(1-value);c.pose=delta@c.pose
    def wheel(n,label):c.commands.append(('wheel',n));scale(1.01**n if n>0 else .99**-n)
    def pairs(n,label):c.commands.append(('pairs',n));scale(.9999**n)
    def shift(value,label):
        c.commands.append(('translate',value))
        if respond:c.pose[:2,2]+=value
    c.wheel=wheel;c.pairs=pairs;c.drag=shift;c.fine_shift=shift
    c.rotate=lambda *a:None
    return c


def desired_scale(factor):
    value=np.diag([factor,factor,1.]);value[:2,2]=300*(1-factor)
    return value


@pytest.mark.parametrize('factor',[1.0007,1.001,1.003,.999,.51,1.5])
def test_scale_motion_converges_with_feedback_sized_batches(factor):
    c=controller()
    assert c.move_to(desired_scale(factor))
    assert all(n<=SCALE_PAIR_BATCH for kind,n in c.commands if kind=='pairs')
    assert abs(math.log(np.hypot(c.pose[0,0],c.pose[1,0])/factor))*200<.12
    route=scale_route(factor);work,batches=scale_work(factor)
    assert batches==len(route)
    assert work==pytest.approx(sum(abs(n)*(.045 if k=='wheel' else .13) for k,n in route))


@pytest.mark.parametrize('factor',[1.5,.5,.999])
def test_scale_saturation_stops_after_one_feedback_and_reports_failure(factor):
    c=controller(respond=False)
    assert not c.move_to(desired_scale(factor))
    assert len(c.commands)==1
    assert c.last_position['reason']=='scale_no_response'


def test_short_budget_does_not_start_cheap_up_step_with_unaffordable_return():
    c=controller(remaining=10)
    assert not c.move_to(desired_scale(1.001))
    assert not c.commands and c.last_position['reason']=='scale_budget'


def test_failed_translation_is_not_reported_as_positioned():
    c=controller(respond=False);desired=np.eye(3);desired[0,2]=10
    assert not c.move_to(desired)
    assert not c.last_position['converged']


@pytest.mark.parametrize('exact',[True,False])
@pytest.mark.parametrize('sample',['same','worse','missing','uncertain'])
def test_cheaper_scale_requires_joint_colour_and_sample_evidence(exact,sample):
    rules=[dict(enabled=True,exact=exact,colors=['#202020'],tolerance=8.,priority=i+1) for i in range(3)]
    row=dict(matrix=desired_scale(1.001),active_indices=[0,1,2],observed_rgb=[[32]*3]*3)
    def field(points,indices):
        colors=np.full((1,3,3),32,np.uint8)
        if sample=='worse':colors[0,2]=200
        return colors,np.full((1,3),sample!='missing'),np.full((1,3),2. if sample=='uncertain' else 0.)
    chosen=prefer_reachable_scale(row,np.eye(3),np.array([[100,300],[300,300],[500,300]]),rules,field)
    if sample=='same':
        assert np.hypot(chosen['matrix'][0,0],chosen['matrix'][1,0])==1.
        assert chosen['scale_alternative']['saved_seconds']>10
    else:assert chosen is row


def test_polishing_stagnation_holds_measured_fallback_across_nested_callers():
    from screenshot_search import actual_result
    rules=[dict(enabled=i==0,exact=True,colors=['#000000'],tolerance=8.,priority=i+1) for i in range(3)]
    def result(color):return dict(actual_result([color,None,None],rules),matrix=np.eye(3),frame=np.zeros((2,2,3)))
    c=controller();c.rules=rules;c.best=result('#000000');c.current=result('#111111')
    c.refinement_anchor=c.best;c._completed_restore=None;c.input_uncertain=False
    c.frame=c.current['frame'];c.actions=[];c.check=lambda:None
    c.register=lambda *a:(np.eye(3),{});c.return_cost=lambda *a,**kw:0.
    reads=[]
    def observe(label):
        reads.append(label);c.current=result('#111111');c.frame=c.current['frame'];return c.current
    c.observe=observe
    assert c.restore()['actual_colors']==['#111111',None,None]
    count=len(reads)
    assert count==4 and not c.current['accepted']
    assert c.restore() is c.current and len(reads)==count
    c.frame=c.frame.copy()  # A genuine state change allows a fresh recovery.
    c.restore()
    assert len(reads)>count
