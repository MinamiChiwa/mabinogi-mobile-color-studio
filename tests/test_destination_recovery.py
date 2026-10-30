"""A selected multi-colour route must not turn into one exact chip plus losses."""
from itertools import permutations
from types import SimpleNamespace

import numpy as np
import pytest

from destination_policy import DestinationPolicy
from refinement_policy import compare_refinement
from screenshot_search import actual_result


def rules(targets=('#000000',)*3, exact=(True,)*3, order=(0,1,2)):
    return [dict(enabled=True,exact=exact[i],colors=[target],tolerance=8.,priority=order.index(i)+1)
            for i,target in enumerate(targets)]


@pytest.mark.parametrize('order',list(permutations(range(3))))
def test_recorded_three_black_correction_preserves_joint_goal(order):
    r=rules(order=order)
    fallback=['#08090D','#0C0A0C','#100F0E']
    intended=['#000000','#050405','#221F1C']
    bad=['#000000','#B57C4E','#C89348']
    p=DestinationPolicy(r,intended,fallback)
    assert not p.improves(bad)
    assert p.rank(intended)<p.rank(bad)
    assert p.improves(['#07080C','#0B090B','#100F0E'])


def test_recorded_small_second_gain_cannot_sacrifice_third():
    r=rules(('#F9F8F1','#A98AAD','#A98AAD'))
    fallback=['#F0EDE4','#A886A7','#97797C']
    bad=['#F0EDE4','#A786A7','#655D68']
    assert not DestinationPolicy(r,fallback,fallback).allows(bad)


def test_mixed_exact_alternatives_similar_and_disabled_regions():
    r=rules(('#000000','#FFFFFF','#FF0000'),exact=(True,False,True))
    r[0]['colors'].append('#010101')
    r[2].update(enabled=False,colors=[])
    p=DestinationPolicy(r,['#000000','#FFFFFF',None],['#010101','#FDFDFD',None])
    assert p.allows(['#000000','#FCFCFC',None])  # Similar stays inside tolerance.
    assert not p.allows(['#020202','#FFFFFF',None])  # Exact remains literal.
    assert not p.allows([None,'#FFFFFF',None])
    assert p.rank([None,'#FFFFFF',None])[0]==float('inf')


def test_global_screenshot_trade_is_allowed_but_additional_loss_is_not():
    r=rules()
    baseline=['#101010','#101010','#101010']
    target=['#000000','#121212','#121212']
    p=DestinationPolicy(r,target,baseline,preserve_baseline=False)
    assert p.allows(target)  # Global priority choice is preserved.
    assert not p.allows(['#000000','#B57C4E','#C89348'])
    assert not compare_refinement(target,baseline,r)['not_worse']


@pytest.mark.parametrize('count',[1,2,3])
@pytest.mark.parametrize('exact',[True,False])
def test_region_counts_and_color_requirements_keep_original_acceptance(count,exact):
    physical=max(2,count)  # A single selected region still has two/three physical cards.
    r=rules(('#FFFFFF',)*physical,exact=(exact,)*physical,order=tuple(range(physical)))
    for i in range(count,physical):r[i].update(enabled=False,colors=[])
    p=DestinationPolicy(r,['#FFFFFF']*physical,['#111111']*physical)
    assert p.improves(['#121212']*physical)
    assert not p.improves(['#101010']*physical)
    assert actual_result(['#FEFEFE']*physical,r)['accepted'] is (not exact)


def test_native_correction_search_and_selection_share_joint_rank(monkeypatch):
    import native_live.route_feedback as m
    import native_live.same_session_dye_planner as planner
    r=rules();fallback=['#08090D','#0C0A0C','#100F0E']
    target=['#000000','#050405','#221F1C'];good=['#07080C','#0B090B','#100F0E']
    bad=['#000000','#B57C4E','#C89348']
    def pose(colors):
        return dict(position=[.5,.5],scale=1.,rotation_degrees=0.,colors=colors)
    def row(colors):
        return dict(input_route=[dict(colors=colors)],final_pose=pose(colors),needed=1.,prediction=dict(colors=colors))
    monkeypatch.setattr(m,'replay_native_route',lambda cp,route,*a,**kw:dict(final_pose=pose(route[0]['colors'] if route else cp['colors'])))
    monkeypatch.setattr(m,'score_native_pose',lambda session,pose,*a,**kw:dict(colors=pose['colors']))
    monkeypatch.setattr(m,'_needed',lambda *a:1.)
    monkeypatch.setattr(m,'compile_periodic_approach',lambda *a,**kw:dict(input_route=[]))
    monkeypatch.setattr(m,'bind_native_route_seeds',lambda *a,**kw:{})
    monkeypatch.setattr(planner,'audit_candidate_endpoint',lambda c,cp,r,row,**kw:row)
    monkeypatch.setattr(planner,'_research_route_allowed',lambda *a:True)
    def pipeline(*a,**kw):
        assert kw['prediction_quality'](dict(colors=good))<kw['prediction_quality'](dict(colors=bad))
        return dict(candidates=[row(bad),row(good)])
    monkeypatch.setattr(m,'search_native_input_pipeline',pipeline)
    context=dict(board=(0,0,100,100),local_size=(100,100),input_coordinate_convention='continuous_screen_edges',
                 settings=dict(minimum_scale=.1,maximum_scale=10.,move_threshold=0.,move_tolerance=0.,scroll_zoom_ratio=.01),
                 wheel_delta_per_step=1.,session=dict(picker_uv=[[.3,.3],[.5,.5],[.7,.7]]))
    args=dict(expected_pose=pose(target),target_pose=pose(target),deadline=1.,clock=lambda:0.)
    selected=m.correct_remaining_route(context,dict(pose=pose(fallback)),r,[dict(colors=fallback)],**args)
    assert selected['prediction']['colors']==good
    # An unusable correction leaves the original route available, not a stop.
    monkeypatch.setattr(m,'search_native_input_pipeline',lambda *a,**kw:dict(candidates=[row(bad)]))
    assert m.correct_remaining_route(context,dict(pose=pose(fallback)),r,[dict(colors=fallback)],**args) is None
    def expired(*a,**kw):raise TimeoutError()
    monkeypatch.setattr(m,'replay_native_route',expired)
    assert m.correct_remaining_route(context,dict(pose=pose(fallback)),r,[dict(colors=fallback)],**args) is None


def test_screenshot_wrong_landing_is_reported_without_promoting_bad_anchor(monkeypatch):
    import screenshot_control as m
    r=rules();baseline=['#08090D','#0C0A0C','#100F0E'];bad=['#000000','#B57C4E','#C89348']
    best=dict(actual_result(baseline,r),frame=np.zeros((4,4,3)),matrix=np.eye(3))
    c=object.__new__(m.Controller)
    c.rules=r;c.current=best;c.best=best;c.refinement_anchor=None;c.observations=[]
    c.frame=best['frame'];c.pose=np.eye(3);c.pose_known=True;c.last_timer=m.time.monotonic()
    c.scene=SimpleNamespace(cards=[(0,0,1,1)]*3)
    c.budget=SimpleNamespace(started=m.time.monotonic(),deadline=m.time.monotonic()+100,remaining=lambda:100,record_cost=lambda *a:None)
    c.owner=SimpleNamespace(event=lambda *a,**kw:None)
    c.progress=lambda *a,**kw:None;c.capture=lambda *a:None;c.write=lambda *a:None;c.check=lambda:None
    monkeypatch.setattr(m,'read_visible',lambda *a,**kw:(bad,[]))
    p=DestinationPolicy(r,['#000000','#050405','#221F1C'],baseline,preserve_baseline=False)
    result=c.observe(destination=p)
    assert result['actual_colors']==bad and result['verified']
    assert not result['destination_consistent']
    assert c.best is best  # Actual text is visible, but cannot lock polishing to this landing.


@pytest.mark.parametrize('positioned',[True,False])
def test_screenshot_bad_landing_returns_then_tries_next_global_proposal(monkeypatch,positioned):
    import screenshot_live as m
    r=rules();baseline=['#08090D','#0C0A0C','#100F0E']
    best=dict(actual_result(baseline,r),matrix=np.eye(3))
    c=SimpleNamespace(rules=r,best=best,current=best,pose=np.eye(3),period=100,
        scene=SimpleNamespace(board=np.array([0,0,100,100]),markers=np.array([[20,20],[50,50],[80,80]])),
        owner=SimpleNamespace(consume_retry_request=lambda:False),
        budget=SimpleNamespace(work_remaining=lambda:100,remaining=lambda:100,record_cost=lambda *a:None),
        return_cost=lambda *a,**kw:0.,write=lambda *a:None,progress=lambda *a,**kw:None)
    samples=SimpleNamespace(period=100,arrays=lambda **kw:([[],[],[]],[[],[],[]]))
    moves=[];restores=[];refinements=[]
    def move_to(matrix):
        moves.append(matrix);return positioned if len(moves)==1 else True
    def observe(label,**kw):
        colors=['#000000','#B57C4E','#C89348'] if len(moves)==1 else ['#000000']*3
        value=actual_result(colors,r)
        if kw.get('destination') is not None:value['destination_consistent']=kw['destination'].allows(colors)
        c.current=value
        return value
    def restore():
        restores.append(True);c.current=c.best;return c.current
    c.move_to=move_to;c.observe=observe;c.restore=restore
    monkeypatch.setattr(m,'_refine',lambda c:refinements.append(True))
    proposals=[dict(matrix=np.eye(3),active_indices=[0,1,2],observed_rgb=[[0,0,0]]*3) for _ in range(2)]
    monkeypatch.setattr(m,'solve',lambda *a,**kw:dict(candidates=proposals))
    assert m._search(c,samples) is samples
    assert len(moves)==2 and len(restores)==1 and not refinements
    assert c.current['accepted']
