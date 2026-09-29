"""Bind integer inputs and their forecast endpoint to freshly scored colours.

This is an input/forecast contract, not a game response certificate. Execution
measures every action and discards remaining bound inputs after a deviation.
"""
from copy import deepcopy
import numpy as np
from atlas_pose import homogeneous, candidate_pose, marker_errors
from input_gestures import planned_gesture
from atlas_pose_scoring import rescore_candidate


# Family penalties are normalized envelope excess, not Delta-E. A value of
# one doubles a hue/lightness allowance; it is not a small colour difference.
# Tolerance failures are valid compromises, but a tiny interpolation change
# at the sampled landing point must not make an otherwise same-family route
# disappear.  The landing probe is a nine-point uncertainty check, so allow a
# small envelope fluctuation while still rejecting a genuine family crossing.
MAX_LANDING_FAMILY_EXCESS = 0.30
# Last-resort cross-family proposals still need to be reasonably close to the
# requested family.  This prevents the fallback tier from publishing a
# visibly unrelated colour merely because its Delta-E happens to be smaller.
MAX_CROSS_FAMILY_EXCESS = 0.35
MAX_CROSS_LANDING_FAMILY_EXCESS = 0.75


def assess_route_stability(gestures, *, board, markers, response_profile_verified=False):
    """Check whether a bound route uses only operation classes we can trust.

    The atlas can predict a colour at a mathematical endpoint, but that does
    not prove the game will consume every rotate/zoom input identically.
    Missing response profiles are recorded for execution feedback and for
    protecting an already observed result during optional candidate trials.
    Tiny rounded arcs and direction reversals remain publication failures.
    """
    reasons=[];directions=[];radius=max(1.,float(np.max(np.linalg.norm(
        np.asarray(markers,float)-np.asarray(markers,float).mean(axis=0),axis=1))))
    rotate_count=wheel_count=drag_count=0
    for gesture in gestures:
        if not gesture.has_effect:
            reasons.append('zero_effect_input');continue
        if gesture.kind=='rotate':
            rotate_count+=1;angle=abs(float(gesture.arc_degrees))
            if angle<.45:reasons.append('rotation_below_measured_response_range')
            if angle>12.25:reasons.append('rotation_exceeds_bound')
        elif gesture.kind=='wheel':
            wheel_count+=1;steps=int(gesture.wheel_steps)
            directions.append(1 if steps>0 else -1)
            if abs(steps)>4:reasons.append('wheel_group_exceeds_calibrated_range')
        elif gesture.kind=='drag':
            drag_count+=1
            if not np.all(np.isfinite(gesture.translation)) or not any(gesture.translation):
                reasons.append('zero_effect_translation')
        else:reasons.append('unsupported_input_kind')
    if any(a!=b for a,b in zip(directions,directions[1:])):
        reasons.append('wheel_direction_reversal')
    # Keep the diagnostics useful even when only translation is used. The
    # radius is recorded for later response-profile calibration.
    return dict(passed=not reasons,reason=reasons[0] if reasons else None,
                reasons=sorted(set(reasons)),radius=radius,
                actions=dict(rotate=rotate_count,wheel=wheel_count,drag=drag_count),
                response_profile=('translation_only' if not (rotate_count or wheel_count)
                                  else ('measured_transform' if response_profile_verified
                                        else 'unverified_transform')),
                response_profile_verified=bool(response_profile_verified))


def forecast_gesture(gesture, board, zoom_down, zoom_up):
    if gesture.kind=='drag':
        return homogeneous(np.column_stack((np.eye(2),gesture.translation)))
    pivot=np.asarray(gesture.anchor,float)-np.asarray(board[:2],float)
    if gesture.kind=='rotate':
        angle=np.radians(gesture.arc_degrees);scale=1.
    elif gesture.kind=='wheel':
        tick=zoom_up if gesture.wheel_steps>0 else zoom_down
        if not np.isfinite(tick) or tick<1e-5:raise ValueError('Invalid route wheel response')
        angle=0.;scale=np.exp(gesture.wheel_steps*tick)
    else:raise ValueError('Unsupported route gesture')
    linear=scale*np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
    return homogeneous(np.column_stack((linear,pivot-linear@pivot)))


def bound_motion(candidate, board, markers, max_steps=80):
    """Validate and expand a binding; never regenerate a different trajectory."""
    route=candidate['planned_route']
    if (route.get('schema')!=1 or tuple(route.get('board',()))!=tuple(board) or
            markers is None or not np.array_equal(route.get('markers'),markers)):
        raise ValueError('Bound route geometry changed')
    inputs=route['inputs']
    if len(inputs)>max_steps:raise ValueError('Bound route exceeds step limit')
    pose=np.eye(3);poses=[];gestures=[];actions=dict(drag=0,rotate=0,wheel=0)
    down=abs(float(candidate.get('zoom_log_step',np.log(1.01))))
    up=float(candidate.get('zoom_log_step_up',down))
    for record in inputs:
        kind=record['kind'];points=record['points']
        if kind=='drag':command=np.subtract(points[-1],points[0])
        elif kind=='rotate':command=record['requested_angle']
        elif kind=='wheel':command=record['wheel_steps']
        else:raise ValueError('Unsupported bound input')
        gesture=planned_gesture(kind,board,command,points[0] if kind!='drag' else None)
        # JSON round-trip changes tuples to lists; compare canonical primitives.
        if (not gesture.has_effect or tuple(map(tuple,points))!=gesture.points or
                record.get('timing')!=gesture.record()['timing'] or
                record.get('right')!=gesture.right or record.get('absolute')!=gesture.absolute or
                record.get('wheel_steps')!=gesture.wheel_steps or
                record.get('arc_start')!=gesture.arc_start):
            raise ValueError('Bound input no longer matches its integer trajectory')
        pose=forecast_gesture(gesture,board,down,up)@pose
        poses.append(pose.copy());gestures.append(gesture);actions[kind]+=1
    target=candidate_pose(candidate,board)
    if (not np.allclose(pose,target,rtol=0,atol=1e-8) or
            not np.allclose(pose,homogeneous(route['endpoint']),rtol=0,atol=1e-8)):
        raise ValueError('Bound route endpoint no longer matches candidate')
    return dict(steps=len(inputs),actions=actions,reachable=True,input_route=inputs,
                actual_pose=pose[:2].tolist(),
                marker_errors=marker_errors(target,pose,np.asarray(markers)-board[:2]).tolist(),
                gestures=gestures,expected_poses=poses,
                response_model='grouped_integer_arc_and_directional_zoom',game_response_verified=False)


def bind_candidate(candidate, atlas, capture_offset, board, markers, rules,
                   now, deadline, *, reference_pose=None, check=lambda:None,
                   require_stable=False, allow_cross_family=False):
    """Compile once, resample the forecast endpoint, then retain the same inputs."""
    from atlas_execution import reposition_budget
    check()
    proposal=deepcopy(candidate)
    proposal.pop('planned_route',None);proposal.pop('execution_budget',None)
    budget=reposition_budget(proposal,now,deadline,board,markers=markers)
    if not budget['allowed']:return None,budget
    # Preserve the configured search neighbourhood, but sample it again at
    # this endpoint. It is a colour-stability check, not a response bound.
    # A production publication must prove that the endpoint remains valid in
    # the measured one-pixel landing neighbourhood. Diagnostic callers retain
    # the old centre-only default so saved-route experiments remain comparable.
    radius=float(proposal.get('landing_radius',1. if require_stable else 0.))
    if not np.isfinite(radius) or radius<0:raise ValueError('Invalid landing neighbourhood')
    offsets=[(0.,0.)]
    if radius:
        offsets.extend((x*radius,y*radius) for y in (-1,0,1) for x in (-1,0,1) if x or y)
    row=rescore_candidate(atlas,capture_offset,proposal,budget['planned_pose'],markers,
                          board,rules,pose_source='bound_integer_route_forecast',
                          reference_pose=reference_pose,screen_offsets=offsets,check=check)
    if row is None:return None,dict(budget,allowed=False,reason='unsupported_endpoint')
    if radius:row.update(landing_radius=radius,landing_sampling='nine_screen_points')
    row['planned_route']=dict(schema=1,board=list(board),markers=np.asarray(markers).tolist(),
        inputs=deepcopy(budget['input_route']),endpoint=deepcopy(budget['planned_pose']),
        proposal_pose=candidate_pose(proposal,board)[:2].tolist(),
        response_model=budget['response_model'],game_response_verified=False)
    row['execution_budget']={k:v for k,v in budget.items() if k!='input_route'}
    bound_motion(row,board,markers)
    route=row['planned_route']
    # The route is still eligible when the transform response profile is
    # incomplete.  Its status is recorded for execution feedback, while each
    # gesture is measured and the remainder is discarded/replanned if the
    # game responds differently.  Treating the missing profile as a hard
    # publication failure made valid sessions report zero candidates.
    response_profile_verified = bool(getattr(atlas,'response_profile_verified',False))
    stability=assess_route_stability(bound_motion(row,board,markers)['gestures'],
                                     board=board,markers=markers,
                                     response_profile_verified=response_profile_verified)
    # ``landing_safe`` means every sampled landing meets the configured
    # colour tolerance.  A compromise can exceed that tolerance while still
    # being a stable, same-family colour.  Use the family envelope for the
    # publication gate and retain the stricter acceptance flag for ranking and
    # UI diagnostics.
    landing_family_maximum=row.get('landing_family_maximum')
    landing_family_safe=bool(row.get('landing_family_safe',row.get('landing_safe',False)))
    if landing_family_maximum is not None:
        try:
            # This deliberately stays stricter than the user's Delta-E
            # tolerance: a compromise may miss the target while it remains a
            # stable member of the requested family.
            landing_family_safe = float(landing_family_maximum) <= MAX_LANDING_FAMILY_EXCESS
        except (TypeError,ValueError):
            landing_family_safe=False
    centre_family_safe=bool(row.get('family_consistent',True))
    samples_complete=bool(row.get('pose_samples',{}).get('complete',True))
    row['route_stability']=dict(stability,landing_safe=bool(row.get('landing_safe',False)),
        landing_family_safe=landing_family_safe,
        landing_maximum=row.get('landing_maximum'),
        landing_family_maximum=row.get('landing_family_maximum'),
        response_model='discrete_route_and_landing_neighbourhood')
    # A cross-family route is a last-resort publication tier.  It is only
    # enabled by the live builder after it has proved that no same-family
    # candidate survived; ordinary binding remains family-safe by default.
    cross_family_allowed = False
    if allow_cross_family:
        try:
            centre_excess = float(row.get('family_maximum', float('inf')))
            landing_excess = float(landing_family_maximum) if landing_family_maximum is not None else float('inf')
            cross_family_allowed = (np.isfinite(centre_excess) and
                                    centre_excess <= MAX_CROSS_FAMILY_EXCESS and
                                    np.isfinite(landing_excess) and
                                    landing_excess <= MAX_CROSS_LANDING_FAMILY_EXCESS)
        except (TypeError, ValueError):
            cross_family_allowed = False
    family_gate = (centre_family_safe and landing_family_safe) or cross_family_allowed
    stable=bool(stability.get('passed')) and family_gate and samples_complete
    row['route_stability']['passed']=stable
    if not stable and stability.get('passed'):
        # Keep the public reason compatible with existing diagnostics; the
        # detailed reasons list identifies a family-only failure.
        reason='landing_neighbourhood_not_stable'
        row['route_stability']['reason']=reason
        details=[reason]
        if not landing_family_safe and not cross_family_allowed: details.append('landing_family_not_stable')
        if allow_cross_family and not (centre_family_safe and landing_family_safe):
            details.append('cross_family_fallback')
        if allow_cross_family and not cross_family_allowed:
            details.append('cross_family_excess_too_large')
        row['route_stability']['reasons']=sorted(set(row['route_stability'].get('reasons',[])+details))
    if allow_cross_family:
        row['cross_family_fallback'] = bool(cross_family_allowed and
                                             not (centre_family_safe and landing_family_safe))
        row['route_stability']['family_gate'] = 'relaxed_cross_family'
    if require_stable and not stable:
        reason='unstable_landing' if stability.get('passed') else 'unstable_route'
        return None,dict(budget,allowed=False,reason=reason,
                         route_stability=row['route_stability'])
    return row,budget
