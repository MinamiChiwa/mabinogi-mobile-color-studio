"""Bounded conditional endpoint-color search over saved routes and macros.

No process reads or input output. Wheel pairs are scored as a whole, allowing
their first event to worsen error. This is not a settled-pose/live predictor.
"""
import copy
import math
import time
from collections import Counter
from input_gestures import wheel_gesture, grouped_rotation_gesture
from native_input_compile import native_drag_gesture
from native_input_response import _pose, replay_native_route
from native_palette_scoring import score_native_pose


def _macros(session, geometry, settings):
    l,t,r,b=geometry.board
    margin=max(10,min(r-l,b-t)*.12)
    def safe(x,y):return (round(min(r-margin,max(l+margin,x))),round(min(b-margin,max(t+margin,y))))
    anchors=list(dict.fromkeys([safe((l+r)/2,(t+b)/2),
              *(safe(l+uv[0]*(r-l),b-uv[1]*(b-t)) for uv in session['picker_uv'])]))
    # Pairs first: bounded discrete offsets, not continuous pivot optimization.
    offsets=[(0,0),*((dx,dy) for d in (1,8,32) for dx,dy in ((d,0),(-d,0),(0,d),(0,-d)))]
    for anchor in anchors:
        for sign in (1,-1):
            first=wheel_gesture(geometry.board,sign,anchor).record()
            for dx,dy in offsets:
                end=(anchor[0]+dx,anchor[1]+dy)
                if l+6 <= end[0] <= r-6 and t+6 <= end[1] <= b-6:
                    yield 'wheel_pair',[first,wheel_gesture(geometry.board,-sign,end).record()]
    for dx,dy in ((d,0) for d in (1,-1,2,-2)):
        try:yield 'drag',[native_drag_gesture(geometry,settings,dx,dy).record()]
        except ValueError:pass
    for dy in (1,-1,2,-2):
        try:yield 'drag',[native_drag_gesture(geometry,settings,0,dy).record()]
        except ValueError:pass
    for anchor in anchors:
        for angle in (.1,-.1,.25,-.25,.5,-.5):
            g=grouped_rotation_gesture(geometry.board,angle,anchor)
            if g.has_effect:yield 'rotate',[g.record()]
        for sign in (1,-1):
            yield 'wheel',[wheel_gesture(geometry.board,sign,anchor).record()]


def _needed(route,verify,safety):
    counts=Counter(g['kind'] for g in route)
    seconds=[float(g['input_seconds']) for g in route]
    if any(not math.isfinite(v) or v<0 for v in seconds):
        raise ValueError('Finite nonnegative input durations required')
    movement=max(sum(v+.15 for v in seconds),
                 counts['rotate']*1.2+counts['wheel']*.5+counts['drag']*1.05)
    return movement+verify+safety


def _select_frontier(rows, count, rank, policy, scale_width, angle_width):
    ordered=sorted(rows,key=rank)
    if policy=='rank_only':return ordered[:count]
    selected=[];seen=set();deferred=[]
    for row in ordered:
        pose=row['final_pose']
        key=(math.floor(pose['scale']/scale_width),
             math.floor(((pose['rotation_degrees']+180)%360-180)/angle_width))
        if key in seen:deferred.append(row)
        else:
            seen.add(key);selected.append(row)
        if len(selected)==count:return selected
    return (selected+deferred)[:count]


def search_native_input_routes(session, routes, reference, geometry, settings, rules, *,
                               sample_policy, wheel_delta_per_step, now, deadline,
                               max_depth=4, beam_width=3, top_k=5, max_candidates=1500,
                               time_budget_seconds=8., verify_seconds=3., safety_seconds=.5,
                               frontier_policy='rank_only',scale_bin_width=.005,angle_bin_degrees=.5,
                               clock=time.monotonic, check=lambda:None,prediction_quality=None):
    """Append finite macros, rank CPU colors, retain best valid saved route.

    Each route starts at the saved initial pose; caller validates capture and
    geometry identity. No requirement to reach a proposal's geometry. Timing
    eligibility is a conservative model allowance, never execution permission.
    All points and wheel events visible; no inertia between gestures assumed.
    """
    check()
    if (frontier_policy not in ('rank_only','scale_angle_diverse')
            or not all(math.isfinite(v) and v>0 for v in (scale_bin_width,angle_bin_degrees))):
        raise ValueError('Explicit frontier policy and positive finite bins required')
    for value,lo,hi in ((max_depth,0,12),(beam_width,1,16),(top_k,1,100),(max_candidates,1,10000)):
        if type(value) is not int or not lo<=value<=hi:raise ValueError('Invalid search limit')
    if (not all(math.isfinite(v) for v in (now,deadline,time_budget_seconds,verify_seconds,safety_seconds,
                                           wheel_delta_per_step))
            or time_budget_seconds<=0 or min(verify_seconds,safety_seconds)<0 or wheel_delta_per_step==0):
        raise ValueError('Finite clocks, positive search budget and explicit wheel calibration required')
    if sample_policy!='all_recorded_points':raise ValueError('Only explicit all-recorded-points search supported')
    reference=_pose(reference)
    if reference!=_pose(session['initial_pose']):raise ValueError('Search reference must be the saved initial pose')
    routes=list(routes)
    if not routes or len(routes)>64:raise ValueError('One to 64 explicit seed routes required')
    if len(rules)!=3 or not any(r['enabled'] for r in rules):raise ValueError('Enabled three-region rules required')
    seeds=[]
    l,t,r,b=geometry.board
    for route in routes:
        route=copy.deepcopy(list(route))
        if len(route)>64 or any(not 1<=len(g['points'])<=128 for g in route):
            raise ValueError('Seed routes exceed bounded input size')
        if any(len(p)!=2 or not all(math.isfinite(v) for v in p)
               or not (l<p[0]<r and t<p[1]<b) for g in route for p in g['points']):
            raise ValueError('Seed input points must be finite and inside the board')
        _needed(route,verify_seconds,safety_seconds)
        seeds.append(route)
    started=clock(); end=started+min(time_budget_seconds,max(0.,deadline-now))
    evaluated=duplicates=budget_rejected=0
    endpoints={}; by_kind=Counter(); completed=0
    expanded=set()
    reason='depth_limit'

    class Expired(Exception):pass
    class CandidateLimit(Exception):pass
    def guard():
        check()
        if clock()>=end:raise Expired()
    if prediction_quality is not None and not callable(prediction_quality):raise ValueError('Invalid prediction ranker')
    def rank(row):return (*(row['prediction']['rank'] if prediction_quality is None else prediction_quality(row['prediction'])),
                           row['needed'],len(row['input_route']))
    def pose_key(pose):return (*pose['position'],pose['scale'],pose['rotation_degrees'])
    def evaluate(base,route,label):
        nonlocal evaluated,duplicates,budget_rejected
        guard()
        if evaluated>=max_candidates:raise CandidateLimit()
        replay=replay_native_route(reference if base is None else base['final_pose'],route,geometry,settings,
                    sample_policy=sample_policy,wheel_delta_per_step=wheel_delta_per_step,check=guard)
        whole=route if base is None else base['input_route']+route
        prediction=score_native_pose(session,replay['final_pose'],rules,check=guard)
        needed=_needed(whole,verify_seconds,safety_seconds)
        guard();evaluated+=1;by_kind[label]+=1
        if needed>deadline-now-max(0.,clock()-started):
            budget_rejected+=1
            return
        pose=replay['final_pose']; key=pose_key(pose)
        history=[] if base is None else base['history']
        row=dict(input_route=whole,final_pose=pose,prediction=prediction,needed=needed,
                 history=history+[dict(kind=label,gestures=len(route),before_pose=reference if base is None else base['final_pose'],
                                      after_pose=pose,trace=replay['trace'])],
                 model_budget_allowed=True,execution_verified=False,game_response_verified=False,
                 release_inertia_modelled=False)
        prior=endpoints.get(key)
        if prior is not None:duplicates+=1
        if prior is None or rank(row)<rank(prior):endpoints[key]=row

    try:
        for seed in seeds:evaluate(None,seed,'seed')
        frontier=_select_frontier(endpoints.values(),beam_width,rank,frontier_policy,scale_bin_width,angle_bin_degrees)
        for depth in range(max_depth):
            guard()
            if frontier and frontier[0]['prediction']['predicted_accepted']:
                reason='predicted_exact';break
            for base in frontier:
                for label,macro in _macros(session,geometry,settings):
                    guard()
                    if len(base['input_route'])+len(macro)<=64:evaluate(base,macro,label)
                expanded.add(pose_key(base['final_pose']))
            completed+=1
            ordered=sorted(endpoints.values(),key=rank)
            if ordered and ordered[0]['prediction']['predicted_accepted']:
                reason='predicted_exact';break
            frontier=_select_frontier([row for row in ordered if pose_key(row['final_pose']) not in expanded],
                           beam_width,rank,frontier_policy,scale_bin_width,angle_bin_degrees)
            if not frontier:
                reason='no_new_endpoints';break
    except Expired:reason='deadline'
    except CandidateLimit:reason='candidate_limit'
    check();elapsed=max(0.,clock()-started);remaining=max(0.,deadline-now-elapsed)
    usable=sorted((r for r in endpoints.values() if r['needed']<=remaining),key=rank)
    for row in usable:row['remaining']=remaining
    return dict(candidates=usable[:top_k],evaluated=evaluated,duplicate_endpoints=duplicates,
                rejected_budget=budget_rejected,expired_after_search=len(endpoints)-len(usable),
                macro_evaluations=dict(by_kind),layers_completed=completed,stop_reason=reason,
                expanded_endpoints=len(expanded),
                frontier_policy=frontier_policy,scale_bin_width=scale_bin_width,angle_bin_degrees=angle_bin_degrees,
                elapsed_seconds=elapsed,execution_seconds_remaining=remaining,capture_id=session['capture_id'],
                execution_verified=False,game_response_verified=False,release_inertia_modelled=False,
                ranking_source='conditional_native_event_endpoint_CPU_colors_then_model_cost',
                optimality='best_in_evaluated_finite_routes_only',
                assumptions='Saved initial reference, axis-aligned explicit UI geometry, all recorded points visible, calibrated wheel events, no between-gesture or release inertia')
