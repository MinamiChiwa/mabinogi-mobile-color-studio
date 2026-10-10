"""Offline wheel-pivot route edits: preserve event count, scale and rotation.

Edits recompile the affected suffix from a replayed prefix. No live input,
inertia prediction, or guarantee beyond finite conditional CPU endpoints.
"""
from dye_regions import validate_region_rules
import copy
import json
import math
import time
from collections import Counter
from input_gestures import wheel_gesture
from native_input_response import _pose, replay_native_route
from native_palette_scoring import score_native_pose
from native_input_route_search import _needed


def refine_native_wheel_pivots(session, routes, reference, geometry, settings, rules, *,
                               sample_policy, wheel_delta_per_step, now, deadline,
                               pixel_steps=(32,8,2,1), beam_width=3, top_k=5,
                               max_candidates=3000, time_budget_seconds=8.,
                               verify_seconds=3., safety_seconds=.5,
                               pivot_grid_radius=0,
                               clock=time.monotonic, check=lambda:None,prediction_quality=None):
    """Move one existing wheel pivot or both adjacent inverse-wheel pivots.

    Rank exact/Delta-E rules at the rebuilt native endpoint, retain old best,
    never append wheel events. Prefix caching is conditional on no inertia.
    Caller validates the session/geometry binding before any future consumer.
    """
    check()
    if type(pivot_grid_radius) is not int or not 0<=pivot_grid_radius<=32:
        raise ValueError('Pivot grid radius must be a whole pixel in [0,32]')
    steps=tuple(pixel_steps)
    if not 1<=len(steps)<=12 or any(type(s) is not int or not 1<=s<=128 for s in steps):
        raise ValueError('One to twelve bounded whole-pixel steps required')
    for v,lo,hi in ((beam_width,1,16),(top_k,1,100),(max_candidates,1,10000)):
        if type(v) is not int or not lo<=v<=hi:raise ValueError('Invalid refinement limit')
    if (not all(math.isfinite(v) for v in (now,deadline,time_budget_seconds,verify_seconds,safety_seconds,
                                         wheel_delta_per_step)) or time_budget_seconds<=0
            or min(verify_seconds,safety_seconds)<0 or wheel_delta_per_step==0):
        raise ValueError('Finite budget and nonzero explicit wheel calibration required')
    if sample_policy!='all_recorded_points':raise ValueError('Explicit full-point assumption required')
    reference=_pose(reference)
    if reference!=_pose(session['initial_pose']):raise ValueError('Saved initial reference required')
    validate_region_rules(session,rules)
    seeds=copy.deepcopy(list(routes))
    if not 1<=len(seeds)<=64:raise ValueError('One to 64 explicit routes required')
    l,t,r,b=geometry.board
    for route in seeds:
        check()
        if len(route)>64 or any(not 1<=len(g['points'])<=128 for g in route):raise ValueError('Route too large')
        if any(len(p)!=2 or not all(math.isfinite(v) for v in p) or not(l<p[0]<r and t<p[1]<b)
               for g in route for p in g['points']):raise ValueError('Seed points must remain within board')
        _needed(route,verify_seconds,safety_seconds)
    start=clock();end=start+min(time_budget_seconds,max(0.,deadline-now))
    evaluated=duplicates=rejected=completed=0
    endpoints={};seen_routes=set();kinds=Counter();reason='steps_exhausted'
    class Expired(Exception):pass
    class Limit(Exception):pass
    class ExactFound(Exception):pass
    def guard():
        check()
        if clock()>=end:raise Expired()
    if prediction_quality is not None and not callable(prediction_quality):raise ValueError('Invalid prediction ranker')
    def rank(row):return (*(row['prediction']['rank'] if prediction_quality is None else prediction_quality(row['prediction'])),
                           row['needed'],len(row['input_route']))
    def replay(pose,route):
        return replay_native_route(pose,route,geometry,settings,sample_policy=sample_policy,
                                   wheel_delta_per_step=wheel_delta_per_step,check=guard)['final_pose']
    def evaluate(route,kind,prefix=None,first=0,edit=None):
        nonlocal evaluated,duplicates,rejected
        guard()
        route_key=json.dumps(route,sort_keys=True,separators=(',',':'))
        if route_key in seen_routes:return
        if evaluated>=max_candidates:raise Limit()
        seen_routes.add(route_key)
        pose=replay(reference if prefix is None else prefix,route if prefix is None else route[first:])
        prediction=score_native_pose(session,pose,rules,check=guard)
        needed=_needed(route,verify_seconds,safety_seconds)
        guard();evaluated+=1;kinds[kind]+=1
        if needed>deadline-now-max(0.,clock()-start):
            rejected+=1;return
        row=dict(input_route=route,final_pose=pose,prediction=prediction,needed=needed,
                 last_edit=edit,model_budget_allowed=True,execution_verified=False,
                 game_response_verified=False,release_inertia_modelled=False)
        key=(*pose['position'],pose['scale'],pose['rotation_degrees'])
        prior=endpoints.get(key)
        if prior is not None:duplicates+=1
        if prior is None or rank(row)<rank(prior):endpoints[key]=row
        return bool(prediction['predicted_accepted'])
    try:
        for route in seeds:evaluate(route,'seed')
        stages=[(step,'pattern') for step in steps]
        if pivot_grid_radius:stages.append((pivot_grid_radius,'grid'))
        for step,mode in stages:
            guard()
            ordered=sorted(endpoints.values(),key=rank)
            if ordered and ordered[0]['prediction']['predicted_accepted']:
                reason='predicted_exact';break
            frontier=ordered[:beam_width]
            editable=False
            for base in frontier:
                route=base['input_route'];prefixes=[reference]
                for gesture in route:prefixes.append(replay(prefixes[-1],[gesture]))
                for index,g in enumerate(route):
                    guard()
                    if g['kind']!='wheel' or not g['wheel_steps']:continue
                    editable=True
                    groups=[([index],'single_pivot')]
                    if (index+1<len(route) and route[index+1]['kind']=='wheel'
                            and route[index+1]['wheel_steps']==-g['wheel_steps']):
                        groups.append(([index,index+1],'pair_common'))
                    for indices,kind in groups:
                        directions=(((dx,dy) for dx in range(-step,step+1) for dy in range(-step,step+1)
                                     if (dx,dy)!=(0,0)) if mode=='grid' else
                                    ((step,0),(-step,0),(0,step),(0,-step),
                                     (step,step),(step,-step),(-step,step),(-step,-step)))
                        label=kind+'_grid' if mode=='grid' else kind
                        for dx,dy in directions:
                            guard()
                            points=[(route[i]['points'][0][0]+dx,route[i]['points'][0][1]+dy) for i in indices]
                            if not all(l+6<=x<=r-6 and t+6<=y<=b-6 for x,y in points):continue
                            proposal=list(route)
                            for i,point in zip(indices,points):
                                proposal[i]=wheel_gesture(geometry.board,route[i]['wheel_steps'],point).record()
                            exact=evaluate(proposal,label,prefixes[index],index,
                                     dict(kind=label,indices=indices,offset=[dx,dy],pixel_step=step))
                            if mode=='grid' and exact:raise ExactFound()
            completed+=1
            if not editable:reason='no_editable_wheels';break
            best=min(endpoints.values(),key=rank) if endpoints else None
            if best and best['prediction']['predicted_accepted']:reason='predicted_exact';break
    except Expired:reason='deadline'
    except Limit:reason='candidate_limit'
    except ExactFound:reason='predicted_exact'
    check();elapsed=max(0.,clock()-start);remaining=max(0.,deadline-now-elapsed)
    usable=sorted((row for row in endpoints.values() if row['needed']<=remaining),key=rank)
    for row in usable:row['remaining']=remaining
    return dict(candidates=usable[:top_k],evaluated=evaluated,duplicate_endpoints=duplicates,
                rejected_budget=rejected,expired_after_search=len(endpoints)-len(usable),
                evaluations_by_kind=dict(kinds),steps_completed=completed,stop_reason=reason,
                elapsed_seconds=elapsed,execution_seconds_remaining=remaining,capture_id=session['capture_id'],
                pivot_grid_radius=pivot_grid_radius,
                execution_verified=False,game_response_verified=False,release_inertia_modelled=False,
                optimality='best_in_finite_evaluated_wheel_pivot_edits_only',
                assumptions='Saved initial reference, explicit axis-aligned UI geometry, all samples visible, calibrated wheel events, no inertia; unchanged event count does not imply unchanged live response')
