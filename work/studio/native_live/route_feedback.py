"""Correct a selected destination from measured motion without a global scan."""
import copy
import time
import numpy as np
from native_input_response import InputGeometry, InputSettings, replay_native_route
from native_palette_scoring import score_native_pose
from native_palette_search import PoseGrid
from native_periodic_route import compile_periodic_approach
from native_input_pipeline import bind_native_route_seeds, search_native_input_pipeline
from native_input_route_search import _needed
from destination_policy import DestinationPolicy


def correct_remaining_route(context, checkpoint, rules, suffix, *, expected_pose, target_pose,
        deadline, clock=time.monotonic, check=lambda:None, admission=lambda row:True):
    """Keep the destination; compare complete corrected routes from actual pose.

    All endpoints are conditionally replayed, never promoted as actual colors.
    Failure to improve returns None and leaves the original suffix available.
    """
    from .same_session_dye_planner import audit_candidate_endpoint, _research_route_allowed
    started=clock()
    if started>=deadline:return None
    geometry=InputGeometry(context['board'],context['local_size'],context['input_coordinate_convention'],
        pixel_mapping=context.get('pixel_mapping'))
    settings=InputSettings(**context['settings'])
    session=dict(context['session'],initial_pose=checkpoint['pose'])
    delta=context['wheel_delta_per_step']
    def guard():
        check()
        if clock()>=deadline:raise TimeoutError('route correction allowance')
    def row(route):
        endpoint=replay_native_route(checkpoint['pose'],route,geometry,settings,
            wheel_delta_per_step=delta,sample_policy='all_recorded_points',check=guard)['final_pose']
        return dict(input_route=copy.deepcopy(route),final_pose=endpoint,
            prediction=score_native_pose(session,endpoint,rules,check=guard),
            needed=_needed(route,3.,.5),source='measured_destination_correction')
    routes=[suffix]
    candidates=[];original=None;target_prediction=None;destination=None
    l,t,r,b=geometry.board;uv=np.asarray(session['picker_uv'])
    markers=np.column_stack((l+uv[:,0]*(r-l),b-uv[:,1]*(b-t)))
    try:
        original=row(suffix)
        target_prediction=score_native_pose(session,target_pose,rules,check=guard)
        destination=DestinationPolicy(rules,target_prediction['colors'],original['prediction']['colors'])
        # This is recovery of an already selected joint destination. Search
        # its colors first, instead of spending the short correction allowance
        # solving the user's global goal again. Publish/compare every completed
        # endpoint under the unchanged user rules below.
        restoration_rules=[dict(rule,exact=True,colors=[color],tolerance=0.)
            if rule['enabled'] else copy.deepcopy(rule)
            for rule,color in zip(rules,target_prediction['colors'])]
        # First restore the intended intermediate pose, then preserve the
        # already optimized remainder. Also compile the original destination
        # directly, since integer rounding can make the first option stall.
        destinations=((expected_pose,suffix),(target_pose,[])) if suffix else ((target_pose,[]),)
        for intermediate,tail in destinations:
            guard()
            compiled=compile_periodic_approach(intermediate,checkpoint['pose'],geometry,settings,markers,
                wheel_delta_per_step=delta,time_budget_seconds=min(.5,max(.001,(deadline-clock())*.3)),
                clock=clock,check=guard)
            if compiled['input_route']:routes.append(compiled['input_route']+tail)
        guard()
        safe=[route for route in routes if len(route)<=64 and _research_route_allowed(route,geometry.board)]
        for route in safe:
            candidate=audit_candidate_endpoint(context,checkpoint,rules,row(route),check=guard)
            candidates.append(candidate)
        bundle=bind_native_route_seeds(session,geometry,settings,safe,
            wheel_delta_per_step=delta,sample_policy='all_recorded_points')
        pose=checkpoint['pose'];x,y=pose['position']
        grid=PoseGrid((x,x),(y,y),1,1,(pose['scale'],),(pose['rotation_degrees'],))
        # Leave part of this same allowance for completed-route audits. Work
        # after the local cutoff may only select already completed candidates.
        remaining=(deadline-clock())*.85
        if remaining>.02:
            now=clock()
            pipeline=search_native_input_pipeline(session,grid,geometry,settings,restoration_rules,
                wheel_delta_per_step=delta,sample_policy='all_recorded_points',now=now,
                deadline=now+remaining+120.,time_budget_seconds=remaining,
                seed_bundle=bundle,generate_target_seeds=False,
                stage_fractions=(.01,.01,.01,.1,.4,.47),clock=clock,check=guard,
                prediction_quality=lambda p:destination.rank(p['colors']),
                route_filter=lambda route:_research_route_allowed(route,geometry.board))
            for candidate in pipeline['candidates']:
                candidate=copy.deepcopy(candidate)
                candidate['prediction']=score_native_pose(session,candidate['final_pose'],rules,check=guard)
                candidate=audit_candidate_endpoint(context,checkpoint,rules,candidate,check=guard)
                candidates.append(candidate)
    except TimeoutError:
        # A local allowance is not the session deadline. Fully audited seeds
        # remain usable; caller's guard still owns F9 and the real cutoff.
        pass
    check()
    if destination is None:return None
    best=None
    for candidate in candidates:
        if not candidate['input_route'] or not admission(candidate):continue
        colors=candidate['prediction']['colors']
        if not destination.improves(colors):continue
        quality=destination.rank(colors)
        rank=(*quality,candidate['needed'],len(candidate['input_route']))
        if best is None or rank<best[0]:best=(rank,candidate)
    if best is None:return None
    selected=copy.deepcopy(best[1])
    selected.update(source='measured_destination_correction',correction_seconds=max(0.,clock()-started),
        target_pose=copy.deepcopy(target_pose),target_colors=target_prediction['colors'],
        uncorrected_prediction=original['prediction'])
    return selected
