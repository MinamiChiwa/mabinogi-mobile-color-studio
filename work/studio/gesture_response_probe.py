"""Finite input-response measurements in an already entered manual session.

This diagnostic does not open a game or a dye, build an atlas, or choose a
colour. The injected game retains all input guards and the game deadline.
Opposite inputs are observations, never assumed to restore the original pose.
"""
from dataclasses import dataclass
import time
import numpy as np
from atlas_pose import homogeneous, marker_errors, pose_fields
from input_gestures import drag_gesture, rotation_gesture, wheel_gesture


@dataclass(frozen=True)
class ProbeAction:
    name: str
    anchor_name: str
    repeat: int
    gesture: object
    variant: str = 'legacy'


@dataclass(frozen=True)
class ZoomReversibilityAction:
    """One wheel notch in a paired reversibility measurement."""
    name: str
    anchor_name: str
    cycle: int
    pair: int
    phase: str
    direction: int
    gesture: object


def zoom_probe_anchors(board):
    """Return conservative center, offset and near-edge client anchors."""
    l, t, r, b = map(int, board)
    w, h = r - l, b - t
    inset_x, inset_y = max(12, round(w * .08)), max(12, round(h * .08))
    return {
        'center': (round((l + r) / 2), round((t + b) / 2)),
        'offset': (round(l + w * .22), round(t + h * .72)),
        'edge': (r - inset_x, t + inset_y),
    }


def zoom_reversibility_plan(board, cycles=3, anchors=None):
    """Build paired +1/-1 and -1/+1 tests for each requested anchor.

    Each pair starts from the frame left by the previous pair.  The return
    action is therefore measured against its pair baseline, never assumed to
    restore the image.  This intentionally exposes cumulative drift.
    """
    if isinstance(cycles, bool) or int(cycles) != cycles or int(cycles) < 1:
        raise ValueError('Probe cycles must be a positive integer')
    cycles = int(cycles)
    available = zoom_probe_anchors(board)
    selected = tuple(available) if anchors is None else tuple(anchors)
    if not selected:
        raise ValueError('At least one probe anchor is required')
    if any(name not in available for name in selected):
        raise ValueError('Unknown probe anchor')
    if len(set(selected)) != len(selected):
        raise ValueError('Probe anchors must be unique')
    result = []
    # Both orders are needed: a single direction pair cannot distinguish
    # directional scale from a state-dependent response. Rotate anchor order
    # on each cycle to reduce confounding between anchor and cumulative zoom.
    orders = ((1, -1), (-1, 1))
    for cycle in range(cycles):
        shift = cycle % len(selected)
        ordered = selected[shift:] + selected[:shift]
        for anchor_name in ordered:
            anchor = available[anchor_name]
            for pair, order in enumerate(orders, 1):
                for phase, direction in zip(('forward', 'return'), order):
                    result.append(ZoomReversibilityAction(
                        name=(f'{anchor_name}_c{cycle + 1:02d}_p{pair}_'
                              f'{phase}_{direction:+d}'),
                        anchor_name=anchor_name, cycle=cycle + 1, pair=pair,
                        phase=phase, direction=direction,
                        gesture=wheel_gesture(board, direction, anchor)))
    return tuple(result)


def response_probe_plan(board):
    l,t,r,b=board
    anchors={'center':(round((l+r)/2),round((t+b)/2)),
             'offset':(round(l+(r-l)*.22),round(t+(b-t)*.72))}
    result=[]
    # Repeat each condition within the same session, preserving the full
    # measured state. An independent later session is still needed to validate.
    for repeat in range(2):
        for name,anchor in anchors.items():
            for angle in (12.,-12.,.4,-.4,.1,-.1):
                result.append(ProbeAction(f'{name}_r{repeat}_a{angle:+g}',name,repeat,
                                         rotation_gesture(board,angle,anchor)))
        for steps in (-1,1):
            result.append(ProbeAction(f'center_r{repeat}_w{steps:+d}','center',repeat,
                                     wheel_gesture(board,steps,anchors['center'])))
    return tuple(result)


def rotation_comparison_plan(board):
    from rotation_comparison import grouped_rotation_gesture
    l,t,r,b=board
    anchors={'center':(round((l+r)/2),round((t+b)/2)),
             'offset':(round(l+(r-l)*.22),round(t+(b-t)*.72))}
    result=[]
    for repeat in range(2):
        variants=(('legacy',rotation_gesture),('grouped',grouped_rotation_gesture))
        if repeat:variants=variants[::-1]
        for name,anchor in anchors.items():
            for angle in (.4,-.4,5.,-5.):
                for variant,make in variants:
                    result.append(ProbeAction(f'{name}_r{repeat}_a{angle:+g}_{variant}',
                        name,repeat,make(board,angle,anchor),variant))
    return tuple(result)


def translation_shared_plan(board, cycles=1):
    """Short, bounded plan for the remaining mechanism evidence.

    It deliberately mixes small translations with a repeated shared pose and
    one wheel pair so the same-session log can compare pose reuse costs without
    spending the whole round on a full rotation matrix sweep.
    """
    l, t, r, b = map(int, board)
    center = (round((l + r) / 2), round((t + b) / 2))
    offset = (round(l + (r - l) * .22), round(t + (b - t) * .72))
    actions = []
    for repeat in range(max(1, int(cycles))):
        for name, anchor in (('center', center), ('offset', offset)):
            for dx, dy in ((8, 0), (-8, 0), (0, 8), (0, -8)):
                actions.append(ProbeAction(
                    f'{name}_r{repeat}_t{dx:+d}_{dy:+d}', name, repeat,
                    # ``drag_gesture`` derives a safe in-board path from the
                    # displacement.  The anchor label is retained as probe
                    # metadata so the same response can be compared at the
                    # two sampling locations; it is not a fourth gesture
                    # argument.
                    drag_gesture(board, dx, dy)))
        actions.extend((
            ProbeAction(f'center_r{repeat}_w-1', 'center', repeat,
                        wheel_gesture(board, -1, center)),
            ProbeAction(f'center_r{repeat}_w+1', 'center', repeat,
                        wheel_gesture(board, 1, center)),
        ))
    return tuple(actions)


def _probe_hex(image, scene, check=lambda: None):
    """Best-effort card HEX read for diagnostics; OCR failure is recorded as null."""
    try:
        from vision import read_codes
        values = read_codes(image, scene.cards, scene.markers, check=check)
        return list(values)
    except Exception as exc:
        if exc.__class__.__name__ in ('Interrupted', 'InterruptedError'):
            raise
        return [None] * len(getattr(scene, 'cards', ()))


def _probe_cursor_trace(game):
    trace = getattr(game, 'last_input_trace', None)
    if trace is None:
        return None
    # Copy the trace so a later gesture cannot mutate the journaled record.
    return [dict(item) for item in trace]


def run_zoom_reversibility_probe(game, scene, reference, snap, log, *,
                                 register=None, clock=time.monotonic,
                                 cycles=3, anchors=None,
                                 mechanism_recorder=None, dye_consumed=None):
    """Measure one-notch zoom pairs without installing a response model.

    The diagnostic sends only ``+1`` and ``-1`` wheel notches.  Every input
    gets its own settled PNG, input trace, optional HEX read and registration;
    the second input in each pair additionally records the composed net pose.
    No compensating input is generated when a pair fails to close.
    """
    if register is None:
        from atlas_runtime import motion as register
    game.check()
    plan = zoom_reversibility_plan(scene.board, cycles=cycles, anchors=anchors)
    local = np.asarray(scene.markers, float) - np.asarray(scene.board[:2], float)
    geometry = tuple(game.geometry())
    park = (int(geometry[2] * .5), int(geometry[3] * .15))
    l, t, r, b = scene.board
    if l <= park[0] <= r and t <= park[1] <= b:
        raise ValueError('No cursor parking position outside the board')
    log('zoom_reversibility_plan', protocol='zoom_reversibility', cycles=int(cycles),
        anchors=list(dict.fromkeys(p.anchor_name for p in plan)),
        actions=[dict(name=p.name, anchor_name=p.anchor_name, cycle=p.cycle,
                      pair=p.pair, phase=p.phase, direction=p.direction,
                      gesture=p.gesture.record()) for p in plan],
        board=list(scene.board), markers=[list(v) for v in scene.markers],
        geometry=list(geometry), dpi=getattr(game, 'response_probe_dpi', None),
        reference='max_sampling', response_model_installed=False)
    recorder_bridge = None
    # This is the HEX read belonging to ``current``.  Keep it alongside the
    # frame so every action can report a true before/after pair.  Unknown OCR
    # remains None and is never reconstructed from a later sample.
    current_hex = None
    if mechanism_recorder is not None:
        from mechanism_experiment import record_probe_event
        recorder_bridge = record_probe_event
        if dye_consumed is not None:
            mechanism_recorder.set_consumption(dye_consumed)
        baseline_hex = _probe_hex(reference, scene, check=game.check)
        current_hex = baseline_hex
        recorder_bridge(mechanism_recorder, 'response_probe_plan',
                        dict(protocol='zoom_reversibility',
                             actions=[dict(name=p.name) for p in plan],
                             markers=[list(v) for v in scene.markers],
                             hex_before=baseline_hex), clock=clock)
        mechanism_recorder.events[-1]['hex_before'] = baseline_hex
        mechanism_recorder.events[-1]['countdown_seconds'] = max(
            0., float(game.until) - float(clock()))
    current = reference
    current_name = 'max_sampling'
    pose = np.eye(3)
    completed = 0
    completed_pairs = 0
    status = 'complete'
    pair_baseline = None
    pair_baseline_name = None
    pair_forward = None
    pair_forward_name = None
    previous_trace = getattr(game, 'capture_input_trace', False)
    game.capture_input_trace = True
    try:
        for index, action in enumerate(plan, 1):
            game.check()
            if tuple(game.geometry()) != geometry:
                raise InterruptedError('Session geometry changed during response measurement')
            gesture = action.gesture
            deadline = min(game.until, getattr(game, 'stage_until', float('inf')))
            if deadline - clock() < gesture.duration + .3 + 2.:
                status = 'game_time_remaining'
                break
            if action.phase == 'forward':
                pair_baseline, pair_baseline_name = current, current_name
                pair_forward = pair_forward_name = None
            before, before_name = current, current_name
            hex_before = current_hex
            countdown_before = max(0., float(game.until) - float(clock()))
            log('zoom_reversibility_command', step=index, name=action.name,
                anchor_name=action.anchor_name, cycle=action.cycle, pair=action.pair,
                phase=action.phase, direction=action.direction,
                reference=before_name, pair_baseline=pair_baseline_name,
                pose_before=pose[:2].tolist(), gesture=gesture.record())
            started = clock()
            game.perform_gesture(gesture)
            input_seconds = clock() - started
            input_trace = _probe_cursor_trace(game)
            log('zoom_reversibility_input', step=index, name=action.name,
                phase=action.phase, direction=action.direction,
                input_elapsed_seconds=input_seconds, input_trace=input_trace)
            game.pause(.15)
            game.check()
            game.move_to(park)
            frame_name = f'zoom_reversibility_{index:03d}_{action.phase}'
            current = snap(frame_name, scene)
            current_name = frame_name
            hexes = _probe_hex(current, scene, check=game.check)
            current_hex = hexes
            details = {}
            registration_started = clock()
            try:
                measured = register(before, current, scene, details)
            except Exception as exc:
                if exc.__class__.__name__ in ('Interrupted', 'InterruptedError'):
                    raise
                measured = None
                details['error'] = str(exc)
            registration_seconds = max(0., float(clock()) -
                                       float(registration_started))
            record = dict(step=index, name=action.name, anchor_name=action.anchor_name,
                          cycle=action.cycle, pair=action.pair, phase=action.phase,
                          direction=action.direction, reference=before_name,
                          pair_baseline=pair_baseline_name, frame=frame_name,
                           gesture=gesture.record(), input_elapsed_seconds=input_seconds,
                           input_trace=input_trace, hex=hexes,
                           hex_before=hex_before, hex_after=hexes,
                           hex_first=None, hex_settled=hexes,
                           countdown_before=countdown_before,
                           countdown_after=max(0., float(game.until) - float(clock())),
                           registration_seconds=registration_seconds,
                           measurements=measured,
                          diagnostics=details,
                          registration_complete=measured is not None)
            if recorder_bridge is not None:
                mechanism_recorder.action(
                    name=action.name, direction=action.direction,
                    step=action.direction, frame_before=before_name,
                    frame_after=frame_name, hex_before=hex_before,
                    hex_after=hexes, hex_first=None, hex_settled=hexes,
                    countdown_before=countdown_before,
                    countdown_after=max(0., float(game.until) - float(clock())),
                    input_seconds=input_seconds, pose=pose[:2].tolist(),
                    residual=details.get('residual'),
                    registration_seconds=registration_seconds,
                    registration_complete=measured is not None,
                    registration_diagnostics=details,
                    protocol='zoom_reversibility', cycle=action.cycle,
                    pair=action.pair, phase=action.phase,
                    measurements=measured)
            if measured is None:
                log('zoom_reversibility_measurement', **record)
                status = 'registration_incomplete'
                break
            matrix = homogeneous(measured['matrix'])
            pose = matrix @ pose
            completed += 1
            record.update(response=pose_fields(matrix, scene.board),
                          marker_errors=marker_errors(np.eye(3), matrix, local).tolist(),
                          cumulative_pose=pose[:2].tolist())
            if action.phase == 'forward':
                pair_forward = matrix
                pair_forward_name = current_name
            else:
                if pair_forward is not None and pair_baseline is not None:
                    # R @ F is the observed net transform from the pair's
                    # baseline, independent of the prior cumulative drift.
                    net = matrix @ pair_forward
                    net_fields = pose_fields(net, scene.board)
                    net_fields['matrix'] = net[:2].tolist()
                    record['pair_net'] = dict(net_fields,
                                              marker_errors=marker_errors(np.eye(3), net, local).tolist(),
                                              baseline=pair_baseline_name,
                                              forward=pair_forward_name,
                                              return_frame=current_name)
                    completed_pairs += 1
                    log('zoom_reversibility_pair', step=index,
                        name=action.name, anchor_name=action.anchor_name,
                        cycle=action.cycle, pair=action.pair,
                        baseline=pair_baseline_name, forward=pair_forward_name,
                        return_frame=current_name, net=record['pair_net'])
            log('zoom_reversibility_measurement', **record)
        outcome = dict(status=status, protocol='zoom_reversibility',
                       planned=len(plan), completed=completed,
                       completed_pairs=completed_pairs, last_frame=current_name,
                       measured_pose=pose[:2].tolist(),
                       response_model_installed=False)
        if status == 'registration_incomplete':
            outcome['measured_pose'] = None
        log('zoom_reversibility_complete', **outcome)
        if recorder_bridge is not None:
            recorder_bridge(mechanism_recorder, 'response_probe_complete',
                            dict(outcome, countdown_seconds=max(
                                0., float(game.until) - float(clock()))),
                            clock=clock)
        return current, outcome
    except Exception as exc:
        log('zoom_reversibility_interrupted', completed=completed,
            completed_pairs=completed_pairs, last_frame=current_name,
            error=str(exc), input_trace=_probe_cursor_trace(game))
        if exc.__class__.__name__ in ('Interrupted', 'InterruptedError'):
            raise
        outcome = dict(status='measurement_failed', protocol='zoom_reversibility',
                       planned=len(plan), completed=completed,
                       completed_pairs=completed_pairs, last_frame=current_name,
                       measured_pose=None, response_model_installed=False,
                       error=str(exc))
        log('zoom_reversibility_complete', **outcome)
        if recorder_bridge is not None:
            recorder_bridge(mechanism_recorder, 'response_probe_complete',
                            dict(outcome, countdown_seconds=max(
                                0., float(game.until) - float(clock())),
                                 status=outcome['status']), clock=clock)
        return current, outcome
    finally:
        game.capture_input_trace = previous_trace
        try:
            game.send(4)
        finally:
            game.send(16)


def run_response_probe(game,scene,reference,snap,log,*,register=None,
                       clock=time.monotonic,protocol='baseline',probe_cycles=3,
                       probe_anchors=None, mechanism_recorder=None,
                       dye_consumed=None, probe_plan='default'):
    """Run a bounded plan; return the last frame and a structured outcome.

    snap(name, scene) preserves original frames. log(kind, **data) journals
    each attempted input before sending it, so interrupted/failed samples stay
    reviewable. Missing registration ends this diagnostic with partial data.
    """
    if register is None:
        from atlas_runtime import motion as register
    # The recorder is an explicit diagnostic opt-in.  It journals evidence
    # only; it never changes the input plan or decides whether dye was used.
    record_probe_event = None
    if mechanism_recorder is not None:
        from mechanism_experiment import record_probe_event
        if dye_consumed is not None:
            mechanism_recorder.set_consumption(dye_consumed)
    game.check()
    if protocol not in ('baseline','rotation_compare','zoom_reversibility'):
        raise ValueError('Unknown response measurement protocol')
    if protocol == 'zoom_reversibility':
        return run_zoom_reversibility_probe(
            game, scene, reference, snap, log, register=register, clock=clock,
            cycles=probe_cycles, anchors=probe_anchors,
            mechanism_recorder=mechanism_recorder, dye_consumed=dye_consumed)
    if probe_plan == 'translation_shared':
        plan = translation_shared_plan(scene.board, cycles=probe_cycles)
    else:
        plan=(rotation_comparison_plan if protocol=='rotation_compare' else response_probe_plan)(scene.board)
    local=np.asarray(scene.markers,float)-scene.board[:2]
    geometry=tuple(game.geometry())
    park=(int(geometry[2]*.5),int(geometry[3]*.15))
    l,t,r,b=scene.board
    if l<=park[0]<=r and t<=park[1]<=b:
        raise ValueError('No cursor parking position outside the board')
    log('response_probe_plan',protocol=protocol,actions=[dict(name=p.name,anchor_name=p.anchor_name,
        repeat=p.repeat,variant=p.variant,gesture=p.gesture.record()) for p in plan],
        board=list(scene.board),markers=[list(v) for v in scene.markers],
        geometry=list(geometry),dpi=getattr(game,'response_probe_dpi',None),
        reference='max_sampling',response_model_installed=False)
    baseline_hex = None
    if record_probe_event is not None:
        baseline_hex = _probe_hex(reference, scene, check=game.check)
        current_hex = baseline_hex
        record_probe_event(mechanism_recorder, 'response_probe_plan',
                           dict(protocol=protocol,
                                actions=[dict(name=p.name) for p in plan],
                                markers=[list(v) for v in scene.markers],
                                hex_before=baseline_hex), clock=clock)
        # Keep the authoritative baseline HEX on the baseline event.  The
        # bridge deliberately does not synthesize values when OCR fails.
        mechanism_recorder.events[-1]['hex_before'] = baseline_hex
        mechanism_recorder.events[-1]['countdown_seconds'] = max(
            0., float(game.until) - float(clock()))
    # Keep the last settled HEX with its corresponding frame.  Without an
    # OCR result, leave it as None rather than borrowing a later sample.
    current_hex = baseline_hex if record_probe_event is not None else None
    current=reference;current_name='max_sampling';pose=np.eye(3);completed=0;skipped=0
    status='complete'
    previous_trace=getattr(game,'capture_input_trace',False)
    game.capture_input_trace=True
    try:
        for index,action in enumerate(plan,1):
            game.check()
            if tuple(game.geometry())!=geometry:
                raise InterruptedError('Session geometry changed during response measurement')
            gesture=action.gesture
            if not gesture.has_effect:
                skipped+=1
                log('response_probe_skipped',step=index,name=action.name,
                    reason='integer_path_has_no_angular_motion',gesture=gesture.record(),variant=action.variant)
                continue
            # A per-action finishing allowance protects the actual countdown;
            # no 60-second elapsed-time cap is added to the workflow.
            deadline=min(game.until,getattr(game,'stage_until',float('inf')))
            if deadline-clock()<gesture.duration+.3+2.:
                status='game_time_remaining';break
            before=current;before_name=current_name
            hex_before=current_hex
            countdown_before=max(0., float(game.until)-float(clock()))
            log('response_probe_command',step=index,name=action.name,
                anchor_name=action.anchor_name,repeat=action.repeat,variant=action.variant,
                reference=before_name,pose_before=pose[:2].tolist(),gesture=gesture.record())
            started=clock()
            game.perform_gesture(gesture)
            input_seconds=clock()-started
            input_trace=getattr(game,'last_input_trace',None)
            log('response_probe_input',step=index,variant=action.variant,
                input_elapsed_seconds=input_seconds,input_trace=input_trace)
            game.pause(.15);game.check();game.move_to(park)
            first_name=f'response_{index:02d}_first'
            first=snap(first_name,scene)
            hex_first = _probe_hex(first, scene, check=game.check) if record_probe_event else None
            game.pause(.15)
            current_name=f'response_{index:02d}_settled'
            current=snap(current_name,scene)
            hex_settled = _probe_hex(current, scene, check=game.check) if record_probe_event else None
            current_hex = hex_settled
            measurements={};diagnostics={}
            registration_started=clock()
            for name,a,z in (('forward',before,current),('reverse',current,before),
                             ('settling',first,current)):
                game.check()
                details={}
                try:
                    measurements[name]=register(a,z,scene,details)
                except Exception as exc:
                    if exc.__class__.__name__ in ('Interrupted','InterruptedError'):
                        raise
                    measurements[name]=None
                    details['error']=str(exc)
                diagnostics[name]=details
            registration_seconds = max(0., float(clock())-float(registration_started))
            record=dict(step=index,name=action.name,anchor_name=action.anchor_name,
                repeat=action.repeat,variant=action.variant,reference=before_name,first=first_name,
                settled=current_name,gesture=gesture.record(),
                input_elapsed_seconds=input_seconds,measurements=measurements,
                input_trace=input_trace,
                diagnostics=diagnostics,pose_before=pose[:2].tolist(),
                hex_before=hex_before,hex_after=hex_settled,
                hex_first=hex_first,hex_settled=hex_settled,
                countdown_before=countdown_before,
                countdown_after=max(0., float(game.until)-float(clock())),
                registration_seconds=registration_seconds,
                registration_complete=all(v is not None for v in measurements.values()))
            # Persist the attempted action even when one registration direction
            # fails; missing motion fields remain absent evidence in the report.
            if record_probe_event is not None:
                record_probe_event(mechanism_recorder, 'response_probe_measurement',
                                   record, clock=clock)
            if not record['registration_complete']:
                log('response_probe_measurement',**record)
                status='registration_incomplete';break
            forward=homogeneous(measurements['forward']['matrix'])
            reverse=homogeneous(measurements['reverse']['matrix'])
            settling=homogeneous(measurements['settling']['matrix'])
            pose=forward@pose;completed+=1
            record.update(pose_after=pose[:2].tolist(),response=pose_fields(forward,scene.board),
                closure_pixels=marker_errors(np.eye(3),reverse@forward,local).tolist(),
                settling_pixels=marker_errors(np.eye(3),settling,local).tolist())
            log('response_probe_measurement',**record)
            # Same one-pixel movement guard as final game-code verification.
            # This is only a stop-for-visible-motion guard, not a precision bound.
            if max(record['settling_pixels'])>1.:
                status='texture_still_moving';break
        outcome=dict(status=status,planned=len(plan),completed=completed,skipped=skipped,
                     last_frame=current_name,measured_pose=pose[:2].tolist(),
                     response_model_installed=False)
        if status=='registration_incomplete':outcome['measured_pose']=None
        log('response_probe_complete',**outcome)
        if record_probe_event is not None:
            record_probe_event(mechanism_recorder, 'response_probe_complete',
                               dict(outcome, countdown_seconds=max(
                                   0., float(game.until)-float(clock()))), clock=clock)
        return current,outcome
    except Exception as exc:
        log('response_probe_interrupted',completed=completed,skipped=skipped,
            last_frame=current_name,error=str(exc),input_trace=getattr(game,'last_input_trace',None))
        if exc.__class__.__name__ in ('Interrupted','InterruptedError'):
            raise
        outcome=dict(status='measurement_failed',planned=len(plan),completed=completed,
                     skipped=skipped,last_frame=current_name,measured_pose=None,
                     response_model_installed=False,error=str(exc))
        log('response_probe_complete',**outcome)
        if record_probe_event is not None:
            record_probe_event(mechanism_recorder, 'response_probe_complete',
                               dict(outcome, countdown_seconds=max(
                                   0., float(game.until)-float(clock()))),
                               clock=clock)
        return current,outcome
    finally:
        game.capture_input_trace=previous_trace
        try:game.send(4)
        finally:game.send(16)
