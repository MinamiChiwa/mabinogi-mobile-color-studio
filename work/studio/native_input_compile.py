"""Bounded offline compilation from conditional native response after each step.

No input is sent. UI geometry, per-point visibility and absence of release
inertia must be validated before any live consumer uses these routes.
"""
from dataclasses import replace
import math
import time
import numpy as np
from atlas_pose import marker_errors, pose_fields
from planner import decompose_gestures
from input_gestures import drag_gesture, grouped_rotation_gesture, wheel_gesture
from native_input_response import replay_native_route, _pose
from native_palette_pose import relative_board_pose


def native_drag_gesture(geometry, settings, dx, dy):
    """For a micro drag, cross the local start gate then return in ONE touch.

    This changes the transient pointer path. Release inertia is not predicted;
    the technique has only conditional offline evidence at present.
    """
    gesture = drag_gesture(geometry.board, dx, dy)
    if not gesture.has_effect:
        return gesture
    start = np.asarray(gesture.points[0], float)
    end = np.asarray(gesture.points[-1], float)
    delta = end-start
    local_delta = geometry.local(end)-geometry.local(start)
    if np.linalg.norm(local_delta) >= settings.move_threshold:
        return gesture
    direction = delta/np.linalg.norm(delta)
    l, t, r, b = geometry.board
    ratios = np.asarray(geometry.local_size)/[r-l, b-t]
    local_per_pixel = np.linalg.norm(direction*ratios)
    reach = math.ceil(settings.move_threshold/local_per_pixel)+1
    # The affine estimate chooses the established kick at 1:1. A measured
    # physical/native staircase may need a longer integer run to cross it.
    while True:
        kick = np.rint(start+direction*reach)
        if not (l+6 <= kick[0] <= r-6 and t+6 <= kick[1] <= b-6):
            raise ValueError('Threshold-crossing drag would leave the safe board')
        if np.linalg.norm(geometry.local(kick)-geometry.local(start)) >= settings.move_threshold:
            break
        if geometry.pixel_mapping is None:
            raise ValueError('Rounded kick failed to cross native start threshold')
        reach += 1
    points = [tuple(int(v) for v in start)]
    for a, z in ((start, kick), (kick, end)):
        count = max(1, min(24, int(np.max(abs(z-a)))))
        points.extend(tuple(round(float(v)) for v in a+(z-a)*i/count)
                      for i in range(1, count+1))
    return replace(gesture, points=tuple(points))


def compile_native_route(target, reference, geometry, settings, markers, *,
                         wheel_delta_per_step, sample_policy, now, deadline,
                         marker_tolerance=.1, max_steps=32, max_proposals=512,
                         verify_seconds=3., safety_seconds=.5,
                         planning_seconds=2., clock=time.monotonic,
                         check=lambda: None,max_wheel_steps=1,input_margin=0.):
    """Greedily reduce marker error with modeled accepted operations.

    A route is conditional, and modelled_reached means geometric tolerance,
    never exact HEX or stable client pose. Each proposal is bounded and the
    current pose advances only via native event replay. No-progress stops.
    """
    check()
    target, reference = _pose(target), _pose(reference)
    timing = (now, deadline, marker_tolerance, verify_seconds, safety_seconds, planning_seconds)
    if (not all(math.isfinite(v) for v in timing) or marker_tolerance <= 0
            or verify_seconds < 0 or safety_seconds < 0 or planning_seconds <= 0):
        raise ValueError('Finite timing and positive tolerance/planning cap required')
    if type(max_steps) is not int or not 0 <= max_steps <= 128:
        raise ValueError('Invalid step limit')
    if type(max_proposals) is not int or not 1 <= max_proposals <= 4096:
        raise ValueError('Invalid proposal limit')
    if sample_policy != 'all_recorded_points':
        raise ValueError('Compiler currently requires explicit all-recorded-points assumption')
    if type(max_wheel_steps) is not int or not 1<=max_wheel_steps<=32 or not math.isfinite(input_margin) or input_margin<0:
        raise ValueError('Invalid standard gesture bounds')
    if not math.isfinite(wheel_delta_per_step) or wheel_delta_per_step == 0:
        raise ValueError('Explicit nonzero wheel calibration required')
    points = np.asarray(markers, float)
    board = geometry.board
    l,t,r,b=board
    gesture_board=(l+input_margin,t+input_margin,r-input_margin,b-input_margin)
    if gesture_board[2]-gesture_board[0]<24 or gesture_board[3]-gesture_board[1]<24:
        raise ValueError('Pointer margin leaves no visible input area')
    if points.shape != (3, 2) or not np.isfinite(points).all():
        raise ValueError('Three finite screen markers required')
    local_markers = points-np.asarray(board[:2])
    desired = relative_board_pose(target, reference, board)
    current = reference
    route, steps = [], []
    evaluated = 0
    unavailable_drags = 0
    last_proposals = []
    actions = dict(rotate=0, wheel=0, drag=0)
    start = clock()
    plan_end = start+min(planning_seconds, max(0., deadline-now))

    def errors(pose):
        return marker_errors(desired, relative_board_pose(pose, reference, board), local_markers)

    reason = 'step_limit'
    for step_index in range(max_steps+1):
        check()
        if clock() >= plan_end:
            reason = 'deadline'
            break
        before = errors(current)
        if float(np.max(before)) <= marker_tolerance:
            reason = 'ok'
            break
        if step_index == max_steps:
            break
        residual = relative_board_pose(target, current, board)
        fields = pose_fields(residual, board)
        pivots = decompose_gestures(fields, board, points)
        proposals = []
        angle = float(np.clip(fields['angle'], -12, 12))
        if abs(angle) > 1e-7:
            for multiplier in (1., .5, 1.5):
                anchor=tuple(np.clip(pivots['rotation_anchor'],[gesture_board[0]+10,gesture_board[1]+10],
                                    [gesture_board[2]-10,gesture_board[3]-10]))
                proposals.append(grouped_rotation_gesture(gesture_board,
                    float(np.clip(angle*multiplier, -12, 12)), anchor))
        if abs(math.log(fields['scale'])) > 1e-9:
            wanted_game_direction = 1 if fields['scale'] > 1 else -1
            adapter_direction = wanted_game_direction*(1 if wheel_delta_per_step > 0 else -1)
            anchor=tuple(np.clip(pivots['zoom_anchor'],[gesture_board[0]+1,gesture_board[1]+1],
                                [gesture_board[2]-1,gesture_board[3]-1]))
            proposals.append(wheel_gesture(board, adapter_direction, anchor))
            if max_wheel_steps>1:
                factor=1+settings.scroll_zoom_ratio*wanted_game_direction
                if factor>0 and factor!=1:
                    count=min(max_wheel_steps,max(1,round(math.log(fields['scale'])/math.log(factor))))
                    if count>1:proposals.append(wheel_gesture(board,adapter_direction*count,anchor))
                # Opposite wheel notches are not reciprocal: their product is
                # 1-ratio^2. Complete two-gesture proposals therefore reach
                # scales between single-direction notches without faking a
                # fractional wheel input. Replay both legs before ranking.
                up=1+settings.scroll_zoom_ratio;down=1-settings.scroll_zoom_ratio
                if 0<down<1<up:
                    wanted=math.log(fields['scale']);pairs=[]
                    for positive in range(1,max_wheel_steps+1):
                        negative=round((wanted-positive*math.log(up))/math.log(down))
                        if 1<=negative<=max_wheel_steps:
                            loss=abs(positive*math.log(up)+negative*math.log(down)-wanted)
                            pairs.append((loss,positive+negative,positive,negative))
                    for _,_,positive,negative in sorted(pairs)[:2]:
                        direction=1 if wheel_delta_per_step>0 else -1
                        pair=(wheel_gesture(board,direction*positive,anchor),
                              wheel_gesture(board,-direction*negative,anchor))
                        # Ordering matters near the actual scale clamps.
                        proposals.extend((pair,pair[::-1]))
        # Translation at three marker landings, including their mean, gives
        # useful alternatives when scale/angle do not quite reach the target.
        current_matrix = relative_board_pose(current, reference, board)
        landed = np.column_stack((local_markers, np.ones(3))) @ (current_matrix@np.linalg.inv(desired)).T
        shifts = local_markers-landed[:, :2]
        translations = [shifts.mean(axis=0), *shifts, np.asarray(pivots['drag'])]
        used = set()
        for move in translations:
            key = tuple(int(v) for v in np.rint(move))
            if key in used or key == (0, 0):
                continue
            used.add(key)
            try:
                proposals.append(native_drag_gesture(geometry, settings, *key))
            except ValueError:
                # A threshold-crossing path can be unavailable under an
                # explicit geometry scenario. Keep other bounded proposals.
                unavailable_drags += 1
        best = None
        last_proposals = []
        for gesture in proposals:
            check()
            if evaluated >= max_proposals:
                reason = 'proposal_limit'
                break
            if clock() >= plan_end:
                reason = 'deadline'
                break
            gestures=gesture if isinstance(gesture,tuple) else (gesture,)
            if len(route)+len(gestures)>max_steps or not all(g.has_effect for g in gestures):
                continue
            records=[g.record() for g in gestures]
            replay = replay_native_route(current, records, geometry, settings,
                        sample_policy=sample_policy, wheel_delta_per_step=wheel_delta_per_step, check=check)
            evaluated += 1
            after = errors(replay['final_pose'])
            last_proposals.append(dict(kind=records[0]['kind'],
                after_max_error=float(np.max(after)), final_pose=replay['final_pose']))
            # Do not accept float32 noise or a stalled geometric operation as progress.
            if float(np.max(after)) >= float(np.max(before))-1e-5:
                continue
            rank = (float(np.max(after)), float(np.mean(after)),sum(g.duration for g in gestures))
            if best is None or rank < best[0]:
                best = (rank, records, replay, after)
        if reason in ('deadline', 'proposal_limit'):
            break
        if best is None:
            reason = 'no_modelled_progress'
            break
        _, records, replay, after = best
        for record in records:
            previous=current;before_leg=errors(previous)
            leg=replay_native_route(previous,[record],geometry,settings,
                sample_policy=sample_policy,wheel_delta_per_step=wheel_delta_per_step,check=check)
            current=leg['final_pose'];after_leg=errors(current)
            steps.append(dict(before_pose=previous,after_pose=current,
                before_max_error=float(np.max(before_leg)),after_max_error=float(np.max(after_leg)),
                diagnostics=leg['diagnostics']))
            route.append(record);actions[record['kind']]+=1
    check()
    elapsed = max(0., clock()-start)
    final_errors = errors(current)
    reached = float(np.max(final_errors)) <= marker_tolerance
    # This remains a conservative allowance, not new measured timing data.
    movement = max(sum(g['input_seconds']+.15 for g in route),
                   actions['rotate']*1.2+actions['wheel']*.5+actions['drag']*1.05)
    needed = movement+verify_seconds+safety_seconds
    remaining = max(0., deadline-now-elapsed)
    allowed = reached and reason == 'ok' and remaining >= needed
    if reason == 'ok' and remaining < needed:
        reason = 'insufficient_time'
    return dict(allowed=allowed, reason=reason, modelled_reached=reached,
                final_pose=current, planned_pose=relative_board_pose(current, reference, board)[:2].tolist(),
                marker_errors=final_errors.tolist(), input_route=route, steps=steps, actions=actions,
                evaluated_proposals=evaluated, planning_elapsed_seconds=elapsed,
                unavailable_drag_proposals=unavailable_drags,
                last_evaluated_proposals=last_proposals,
                needed=needed, remaining=remaining, sample_policy=sample_policy,
                response_model='conditional_native_response_at_each_compilation_step',
                execution_verified=False, game_response_verified=False, release_inertia_modelled=False,
                assumptions='Explicit axis-aligned UI geometry, all points visible, one event per wheel notch, no release inertia drift')
