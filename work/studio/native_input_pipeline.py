"""Shared-budget offline pose, route, macro and pivot search.

No process or input adapter. Historical routes require explicit capture,
pixel, geometry, settings and sample-policy binding, never a global cache.
"""
from dye_regions import validate_region_rules
import copy
from dataclasses import asdict
import hashlib
import itertools
import json
import math
import time
import numpy as np
from input_gestures import grouped_rotation_gesture, wheel_gesture
from native_input_response import _pose, replay_native_route
from native_palette_scoring import score_native_pose
from native_palette_search import PoseGrid
from native_target_seeds import target_seed_poses
from native_input_compile import compile_native_route
from native_input_route_search import _needed, _select_frontier, search_native_input_routes
from native_input_pivot_refine import refine_native_wheel_pivots


def _binding(session, geometry, settings, delta, policy):
    binding = dict(capture_id=session['capture_id'], reference=_pose(session['initial_pose']),
        pixel_sha256=[hashlib.sha256(np.asarray(p,dtype=np.uint8).tobytes()).hexdigest() for p in session['pixels']],
        picker_uv=session['picker_uv'], color_preserve_ratio=session['color_preserve_ratio'],
        board=geometry.board, local_size=geometry.local_size,
        input_coordinate_convention=geometry.input_coordinate_convention,settings=asdict(settings),
        wheel_delta_per_step=delta, sample_policy=policy)
    if geometry.pixel_mapping is not None:
        binding['pixel_mapping'] = geometry.pixel_mapping_record()
    return binding


def _validate_routes(routes,geometry):
    routes=copy.deepcopy(list(routes))
    if not 1<=len(routes)<=64:raise ValueError('One to 64 explicit routes required')
    l,t,r,b=geometry.board
    for route in routes:
        if len(route)>64 or any(not 1<=len(g['points'])<=128 for g in route):raise ValueError('Route too large')
        if any(g['kind'] not in ('drag','rotate','wheel') for g in route):raise ValueError('Unsupported input record')
        if any(len(p)!=2 or not all(math.isfinite(v) for v in p) or not(l<p[0]<r and t<p[1]<b)
               for g in route for p in g['points']):raise ValueError('Input point outside board')
        _needed(route,3.,.5)
    return routes


def bind_native_route_seeds(session,geometry,settings,routes,*,wheel_delta_per_step,sample_policy):
    """Bind saved routes for re-evaluation, not live authenticity/permission."""
    if sample_policy!='all_recorded_points' or not math.isfinite(wheel_delta_per_step) or wheel_delta_per_step==0:
        raise ValueError('Explicit full-point policy and calibrated nonzero wheel required')
    binding=_binding(session,geometry,settings,wheel_delta_per_step,sample_policy)
    return dict(schema=1,binding=copy.deepcopy(binding),routes=_validate_routes(routes,geometry))


def search_native_input_pipeline(session,grid,geometry,settings,rules,*,wheel_delta_per_step,
        sample_policy,now,deadline,time_budget_seconds=20.,seed_bundle=None,
        generate_target_seeds=True,shortlist=24,top_k=5,max_coarse=6000,
        max_structural=500,macro_candidates=1500,pivot_candidates=5000,
        pivot_grid_radius=32,stage_fractions=(.15,.15,.20,.10,.15,.25),
        clock=time.monotonic,check=lambda:None,route_filter=None,target_poses=None,prediction_quality=None):
    """Finite conditional search; all preparation stages debit one deadline.

    Historical bound routes are optional. Fresh runs take palette/rules/grid,
    no recorded target pose. Geometrically unreached compiler endpoints may
    be color-search seeds; their rejected geometry allowance is not inherited.
    Final model budget and CPU acceptance remain separate from live success.
    """
    check();start=clock()
    if not isinstance(grid,PoseGrid):raise ValueError('PoseGrid required')
    validate_region_rules(session,rules)
    if not all(math.isfinite(v) for v in (now,deadline,time_budget_seconds,wheel_delta_per_step)) or time_budget_seconds<=0 or wheel_delta_per_step==0:
        raise ValueError('Finite clocks, positive budget and explicit wheel required')
    if sample_policy!='all_recorded_points':raise ValueError('Only full-recorded-points pipeline supported')
    if route_filter is not None and not callable(route_filter):raise ValueError('Route filter must be callable')
    for v,lo,hi in ((shortlist,1,64),(top_k,1,64),(max_coarse,1,10000),(max_structural,1,10000),
                    (macro_candidates,1,10000),(pivot_candidates,1,10000),(pivot_grid_radius,0,32)):
        if type(v) is not int or not lo<=v<=hi:raise ValueError('Invalid candidate/grid limit')
    fractions=tuple(stage_fractions)
    if len(fractions)!=6 or not all(math.isfinite(v) and v>0 for v in fractions) or sum(fractions)>1+1e-9:
        raise ValueError('Six positive stage fractions must fit total budget')
    reference=_pose(session['initial_pose']);binding=_binding(session,geometry,settings,wheel_delta_per_step,sample_policy)
    supplied=[] if target_poses is None else [_pose(p) for p in target_poses]
    saved=[]
    if seed_bundle is not None:
        if seed_bundle.get('schema')!=1 or json.dumps(seed_bundle.get('binding'),sort_keys=True)!=json.dumps(binding,sort_keys=True):
            raise ValueError('Route seed binding differs from capture/pixels/reference/geometry/settings/calibration')
        saved=_validate_routes(seed_bundle['routes'],geometry)
    end=start+min(time_budget_seconds,max(0.,deadline-now));phase_end=end
    stages=dict(initial=None,target_seed=None,coarse=None,compile=None,structural=None,macro=None,pivot=None)
    counts=dict(coarse=0,compile=0,structural=0,macro=0,pivot=0)
    endpoints={};poses=list(supplied);coarse=[];reason='completed';rejected_routes=0
    l,t,r,b=geometry.board
    markers=[[l+uv[0]*(r-l),b-uv[1]*(b-t)] for uv in session['picker_uv']]

    class Deadline(Exception):pass
    class StageDeadline(Exception):pass
    def guard():
        check()
        if clock()>=end:raise Deadline()
    def stage_guard():
        guard()
        if clock()>=phase_end:raise StageDeadline()
    if prediction_quality is not None and not callable(prediction_quality):raise ValueError('Invalid prediction ranker')
    def rank(row):return (*(row['prediction']['rank'] if prediction_quality is None else prediction_quality(row['prediction'])),
                           row['needed'],len(row['input_route']))
    def usable():
        remaining=max(0.,deadline-now-max(0.,clock()-start))
        return sorted((row for row in endpoints.values() if row['needed']<=remaining),key=rank)
    def exact():
        rows=usable();return bool(rows and rows[0]['prediction']['predicted_accepted'])
    def retain(route,pose,prediction,source):
        nonlocal rejected_routes
        if route_filter is not None:
            guard();allowed=route_filter(copy.deepcopy(route));guard()
            if type(allowed) is not bool:raise ValueError('Route filter must return a boolean')
            if not allowed:rejected_routes+=1;return
        needed=_needed(route,3.,.5)
        if needed>deadline-now-max(0.,clock()-start):return
        key=(*pose['position'],pose['scale'],pose['rotation_degrees'])
        row=dict(input_route=route,final_pose=pose,prediction=prediction,source=source,needed=needed,
            capture_id=session['capture_id'],model_budget_allowed=True,execution_verified=False,
            game_response_verified=False,release_inertia_modelled=False)
        prior=endpoints.get(key)
        if prior is None or rank(row)<rank(prior):endpoints[key]=row
    def evaluate(route,source,checker):
        checker()
        pose=replay_native_route(reference,route,geometry,settings,sample_policy=sample_policy,
                 wheel_delta_per_step=wheel_delta_per_step,check=checker)['final_pose']
        prediction=score_native_pose(session,pose,rules,check=checker)
        checker();retain(route,pose,prediction,source)
    def phase(name,index,action):
        nonlocal phase_end
        guard();began=clock()
        cap=max(0.,end-began) if name=='pivot' else min(time_budget_seconds*fractions[index],max(0.,end-began))
        phase_end=began+cap;stages[name]=dict(cap_seconds=cap,stop_reason='completed')
        try:
            details=action(cap)
            if details:stages[name].update(details)
        except StageDeadline:stages[name]['stop_reason']='stage_deadline'
        finally:stages[name]['elapsed_seconds']=max(0.,clock()-began)
    def targets(cap):
        if not generate_target_seeds:return dict(stop_reason='disabled',generated=0)
        result=target_seed_poses(session,rules,scales=grid.scales,rotations_degrees=grid.rotations_degrees,
           pixels_per_region=8,reference=reference,max_candidates=2000,time_budget_seconds=cap,
           subpixel_fractions=(0.,.5),clock=clock,check=guard)
        poses.extend(result['poses']);return {k:v for k,v in result.items() if k not in ('poses','seeds')}
    def coarse_stage(cap):
        seen=set()
        for pose in itertools.chain([reference],poses,grid.poses()):
            stage_guard()
            if counts['coarse']>=max_coarse:return dict(stop_reason='candidate_limit')
            key=(*pose['position'],pose['scale'],pose['rotation_degrees'])
            if key in seen:continue
            seen.add(key);prediction=score_native_pose(session,pose,rules,check=stage_guard)
            coarse.append(dict(prediction=prediction,final_pose=pose,input_route=[],needed=0.))
            counts['coarse']+=1
    def compile_stage(cap):
        selected=_select_frontier(coarse,shortlist,rank,'scale_angle_diverse',.005,.5)
        for row in selected:
            stage_guard()
            current=now+max(0.,clock()-start)
            compiled=compile_native_route(row['final_pose'],reference,geometry,settings,markers,
                 wheel_delta_per_step=wheel_delta_per_step,sample_policy=sample_policy,now=current,deadline=deadline,
                 max_steps=16,max_proposals=128,planning_seconds=max(.001,min(.2,phase_end-clock())),
                 clock=clock,check=stage_guard)
            evaluate(compiled['input_route'],'compiled_model_endpoint',stage_guard)
            counts['compile']+=1
    def structural_stage(cap):
        bases=_select_frontier(usable(),min(16,shortlist),rank,'scale_angle_diverse',.005,.5)
        seen=set()
        for base in bases:
            route=base['input_route'];movable=[i for i,g in enumerate(route) if g['kind'] in ('wheel','rotate')][:5]
            def variants():
                for keep in itertools.product((False,True),repeat=len(movable)):
                    dropped={i for i,v in zip(movable,keep) if not v}
                    yield [g for i,g in enumerate(route) if i not in dropped]
                for i,g in enumerate(route):
                    if g['kind']=='rotate':
                        for angle in (-3.,-2.,-1.,-.5,.5,1.,2.,3.):
                            replacement=grouped_rotation_gesture(geometry.board,angle,g['points'][0])
                            if replacement.has_effect:yield route[:i]+[replacement.record()]+route[i+1:]
                    elif g['kind']=='wheel':yield route[:i]+[wheel_gesture(geometry.board,-g['wheel_steps'],g['points'][0]).record()]+route[i+1:]
            for route_variant in variants():
                stage_guard()
                if counts['structural']>=max_structural:return dict(stop_reason='candidate_limit')
                key=json.dumps(route_variant,sort_keys=True)
                if key in seen:continue
                seen.add(key);evaluate(route_variant,'structural_edit',stage_guard);counts['structural']+=1
    def macro_stage(cap):
        seeds=_select_frontier(usable(),min(24,shortlist),rank,'scale_angle_diverse',.005,.5)
        if not seeds:return dict(stop_reason='no_candidates')
        result=search_native_input_routes(session,[r['input_route'] for r in seeds],reference,geometry,settings,rules,
            wheel_delta_per_step=wheel_delta_per_step,sample_policy=sample_policy,now=now+clock()-start,deadline=deadline,
            max_candidates=macro_candidates,max_depth=4,beam_width=5,top_k=min(24,shortlist),
            time_budget_seconds=cap,frontier_policy='scale_angle_diverse',clock=clock,check=guard,
            prediction_quality=prediction_quality)
        counts['macro']=result['evaluated']
        for row in result['candidates']:retain(row['input_route'],row['final_pose'],row['prediction'],'macro_endpoint')
        return {k:v for k,v in result.items() if k!='candidates'}
    def pivot_stage(cap):
        seeds=_select_frontier(usable(),min(24,shortlist),rank,'scale_angle_diverse',.005,.5)
        if not seeds:return dict(stop_reason='no_candidates')
        result=refine_native_wheel_pivots(session,[r['input_route'] for r in seeds],reference,geometry,settings,rules,
            wheel_delta_per_step=wheel_delta_per_step,sample_policy=sample_policy,now=now+clock()-start,deadline=deadline,
            max_candidates=pivot_candidates,beam_width=3,top_k=top_k,pixel_steps=(64,32,8,2,1),
            pivot_grid_radius=pivot_grid_radius,time_budget_seconds=cap,clock=clock,check=guard,
            prediction_quality=prediction_quality)
        counts['pivot']=result['evaluated']
        for row in result['candidates']:retain(row['input_route'],row['final_pose'],row['prediction'],'pivot_endpoint')
        return {k:v for k,v in result.items() if k!='candidates'}
    try:
        guard();evaluate([],'identity',guard)
        for route in saved:evaluate(route,'bound_saved_route',guard)
        stages['initial']=dict(bound_saved_routes=len(saved),stop_reason='completed')
        actions=[('target_seed',targets),('coarse',coarse_stage),('compile',compile_stage),
                 ('structural',structural_stage),('macro',macro_stage),('pivot',pivot_stage)]
        for index,(name,action) in enumerate(actions):
            if exact():reason='predicted_exact';break
            phase(name,index,action)
        if exact():reason='predicted_exact'
    except Deadline:reason='deadline'
    check();elapsed=max(0.,clock()-start);remaining=max(0.,deadline-now-elapsed)
    rows=sorted((row for row in endpoints.values() if row['needed']<=remaining),key=rank)[:top_k]
    for row in rows:row['remaining']=remaining
    return dict(candidates=rows,stages=stages,evaluated=counts,stop_reason=reason,
        route_filter_applied=route_filter is not None,route_filter_rejections=rejected_routes,
        predicted_exact=bool(rows and rows[0]['prediction']['predicted_accepted']),
        elapsed_seconds=elapsed,search_budget_seconds=min(time_budget_seconds,max(0.,deadline-now)),
        execution_seconds_remaining=remaining,capture_id=session['capture_id'],
        seed_mode='bound_saved_routes_and_fresh_candidates' if saved else 'fresh_palette_HEX_search',
        execution_verified=False,game_response_verified=False,release_inertia_modelled=False,
        optimality='finite shared-budget heuristic only',
        assumptions='Saved initial reference, explicit UI geometry/settings/wheel/full-point policy and no inertia; binding is offline identity, not live authenticity')
