"""Bounded offline local refinement, admitted only with checked prefix returns.

Every published endpoint is replayed and scalar-scored. The finite return
neighborhood is conditional model evidence, not a promise about live motion;
the controller must verify actual return quality and its protected visual anchor.
No wheel operation is admitted: opposite scroll notches are not inverses.
"""
import copy
import itertools
import json
import math
import time

import numpy as np

from input_gestures import PointerGesture
from native_input_compile import native_drag_gesture
from native_input_response import (InputGeometry, InputSettings, replay_native_route,
    apply_motion_event, virtual_rotation_delta)
from native_input_route_search import _needed
from native_palette_scoring import score_native_pose
from .compromise import observed_quality, predicted_quality, quality_fields


class _Expired(Exception):
    pass


def _guard(deadline, clock, check):
    if type(deadline) not in (int, float) or not math.isfinite(deadline):
        raise ValueError('Finite local-search deadline required')
    def guard():
        if clock() >= deadline:
            raise _Expired()
        try:
            check()
        except TimeoutError:
            # The supplied IO guard uses this same local phase deadline. A
            # read crossing it exhausts this search, leaving reserved recovery
            # attempts available. Earlier/global IO failures still propagate.
            if clock() >= deadline:
                raise _Expired() from None
            raise
        if clock() >= deadline:
            raise _Expired()
    return guard


def _geometry(context):
    return (InputGeometry(context['board'], context['local_size'],
                          context['input_coordinate_convention'],
                          pixel_mapping=context.get('pixel_mapping')),
            InputSettings(**context['settings']))


def _row(context, checkpoint, rules, route, guard, source):
    geometry, settings = _geometry(context)
    endpoint = replay_native_route(checkpoint['pose'], route, geometry, settings,
        wheel_delta_per_step=context['wheel_delta_per_step'],
        sample_policy='all_recorded_points', check=guard)['final_pose']
    return dict(input_route=copy.deepcopy(route), final_pose=endpoint,
        prediction=score_native_pose(context['session'], endpoint, rules, check=guard),
        needed=_needed(route, 3., .5), source=source)


def _endpoint_checkpoint(context, checkpoint, pose, guard):
    neutral = [dict(enabled=True, exact=True, colors=['#000000'], tolerance=0.)] * 3
    codes = score_native_pose(context['session'], pose, neutral, check=guard)['colors']
    return dict(copy.deepcopy(checkpoint), pose=copy.deepcopy(pose), client_hex=codes)


def _inverse(gesture, geometry, settings):
    if gesture['kind'] == 'drag':
        dx, dy = np.asarray(gesture['points'][-1])-gesture['points'][0]
        return native_drag_gesture(geometry, settings, -int(dx), -int(dy)).record()
    if gesture['kind'] != 'rotate':
        raise ValueError('Only drag and rotation have supported audited returns')
    points = (tuple(gesture['points'][0]),
              *(tuple(p) for p in reversed(gesture['points'][gesture['arc_start']:])))
    return PointerGesture('rotate', points, right=True,
        requested_angle=-gesture['requested_angle'], arc_start=1).record()


def _return_neighborhood(context, pose, rules, route, baseline_quality, guard):
    geometry, settings = _geometry(context)
    worst = None
    samples = 0
    for dx, dy, scale, rotation in itertools.product((-1, 0, 1), repeat=4):
        guard()
        nearby = copy.deepcopy(pose)
        nearby['position'] = np.asarray(np.asarray(pose['position'], dtype=np.float32)+
            np.asarray([dx*2e-7, dy*2e-7], dtype=np.float32), dtype=np.float32).tolist()
        nearby['scale'] = float(np.float32(pose['scale']+scale*1e-7))
        nearby['rotation_degrees'] = float(np.float32(pose['rotation_degrees']+rotation*1e-5))
        endpoint = replay_native_route(nearby, route, geometry, settings,
            wheel_delta_per_step=context['wheel_delta_per_step'],
            sample_policy='all_recorded_points', check=guard)['final_pose']
        quality = predicted_quality(score_native_pose(context['session'], endpoint,
                                                      rules, check=guard), rules)
        if quality > baseline_quality:
            return None
        worst = quality if worst is None else max(worst, quality)
        samples += 1
    guard()
    return dict(samples=samples, all_samples_baseline_or_better=True,
        position_radius=2e-7, scale_radius=1e-7, rotation_radius_degrees=1e-5,
        worst_return_quality=worst,
        scope='Finite float32 endpoint neighborhood; live recovery requires readback')


def _protect(context, checkpoint, rules, candidate, baseline_quality, guard, stats=None):
    from .same_session_dye_planner import audit_candidate_endpoint
    row = audit_candidate_endpoint(context, checkpoint, rules, candidate, check=guard)
    geometry, settings = _geometry(context)
    returns = []
    for index in range(1, len(row['input_route'])+1):
        prefix = row['input_route'][:index]
        endpoint = replay_native_route(checkpoint['pose'], prefix, geometry, settings,
            wheel_delta_per_step=context['wheel_delta_per_step'],
            sample_policy='all_recorded_points', check=guard)['final_pose']
        reference = _endpoint_checkpoint(context, checkpoint, endpoint, guard)
        route = [_inverse(g, geometry, settings) for g in reversed(prefix)]
        recovery = _row(context, reference, rules, route, guard, 'prepared_prefix_return')
        recovery = audit_candidate_endpoint(context, reference, rules, recovery, check=guard)
        quality = predicted_quality(recovery['prediction'], rules)
        if quality > baseline_quality:
            return None
        neighborhood = _return_neighborhood(context, endpoint, rules, route,
                                             baseline_quality, guard)
        if stats is not None:
            stats['return_checked'] += 1
        if neighborhood is None:
            return None
        recovery.update(prefix_index=index, recovery_quality=quality,
                        neighborhood_audit=neighborhood)
        returns.append(recovery)
    guard()
    row.update(prefix_recoveries=returns,
        recovery_route=copy.deepcopy(returns[-1]['input_route']),
        recovery_candidate=copy.deepcopy(returns[-1]),
        baseline_quality=baseline_quality,
        refinement_quality=predicted_quality(row['prediction'], rules),
        recovery_quality=returns[-1]['recovery_quality'],
        refinement_metrics=quality_fields(row['prediction'], rules),
        ready_for_input=False,
        protection_audit=dict(every_prefix_has_checked_return=True,
            prefix_count=len(returns), actual_return_verified=False))
    return row


def _rotation(anchor, radius, sign, geometry=None):
    """One integer arc edge after a radial move, in a standard right touch."""
    a = (anchor[0]+radius, anchor[1])
    b = ((anchor[0]+radius, anchor[1]+1) if geometry is None else
         geometry.native_tangent_point(a))
    points = (anchor, a, b) if sign < 0 else (anchor, b, a)
    # Pointer arc degrees use screen-down Y; native rotation uses screen-up Y.
    return PointerGesture('rotate', points, right=True,
        requested_angle=-sign*.3, arc_start=1).record()


def _offsets(radius, step=1):
    values = range(-radius, radius+1, step)
    return sorted(((x, y) for x in values for y in values),
                  key=lambda p: (max(abs(p[0]), abs(p[1])), abs(p[0])+abs(p[1]), p))


def _local_proposals(context, pose, radius_pixels, guard):
    """Finite small arcs, scored with native event kernels before full audit.

    Every distinct pivot/radius event is compiled through real route replay.
    Applying those events avoids repeatedly parsing unchanged descriptors and
    geometry; _protect still independently replays every original point.
    """
    from .same_session_dye_planner import _research_route_allowed
    geometry, settings = _geometry(context)
    for dx, dy in _offsets(radius_pixels):
        if dx or dy:
            guard()
            route = [native_drag_gesture(geometry, settings, dx, dy).record()]
            if _research_route_allowed(route, context['board']):
                endpoint = replay_native_route(pose, route, geometry, settings,
                    wheel_delta_per_step=context['wheel_delta_per_step'],
                    sample_policy='all_recorded_points', check=guard)['final_pose']
                yield 'integer_drags', route, endpoint
    l, t, r, b = geometry.board
    anchor = (round((l+r)/2), round((t+b)/2))
    extent = min(r-l, b-t)
    angles = []
    events = {}
    zero = dict(position=[0., 0.], scale=1., rotation_degrees=0.)
    def event(point, radius, sign):
        key = (point, radius, sign)
        if key not in events:
            guard()
            route = [_rotation(point, radius, sign, geometry if geometry.pixel_mapping is not None else None)]
            if not _research_route_allowed(route, context['board']):
                events[key] = None
            else:
                replay = replay_native_route(zero, route, geometry, settings,
                    wheel_delta_per_step=context['wheel_delta_per_step'],
                    sample_policy='all_recorded_points', check=guard)
                delta = replay['final_pose']['rotation_degrees']
                # Preserve each accepted event, including zero rotations. The
                # physical lattice can reject one arc point or collapse both.
                accepted = tuple(row['rotation_delta'] for row in replay['trace'])
                events[key] = (route[0], geometry.normalized(geometry.local(point)), delta, accepted)
        return events[key]
    def apply_compiled(start, compiled):
        for delta in compiled[3]:
            start = apply_motion_event(start, compiled[1], [0, 0], 1., delta, settings)
        return start
    for radius in range(max(8, round(extent*.26)), max(9, round(extent*.44))+1):
        guard()
        compiled = event(anchor, radius, -1)
        if compiled is not None and compiled[2]:
            angles.append((radius, compiled[2]))
    seeds = []
    # Fine net rotations are deliberately first: the saved rc12 sessions have
    # useful basins around 0.001--0.01 degrees that the old coarse family
    # (0.02/0.04) cannot see.
    for wanted in (-.001, .001, -.005, .005, -.01, .01, -.02, .02, -.04, .04):
        pairs = [(abs((a-b)-wanted), ra, rb)
                 for ra, a in angles for rb, b in angles
                 if (a-b)*wanted > 0 and abs(a-b) <= .06]
        seeds.extend((wanted, ra, rb) for _, ra, rb in sorted(pairs)[:3])
    if angles:
        for index in (0, len(angles)//2, len(angles)-1):
            radius = angles[index][0]
            seeds.append((0., radius, radius))
    seeds = list(dict.fromkeys(seeds))
    first_endpoints = {}
    for _, ra, _ in seeds:
        if ra not in first_endpoints:
            compiled = event(anchor, ra, -1)
            first_endpoints[ra] = apply_compiled(pose, compiled)
    seen = set()
    fine_radius = min(12, max(5, math.floor(extent*.08)))
    coarse_radius = min(40, max(5, math.floor(extent*.08/5)*5))
    fine_points = _offsets(fine_radius)
    coarse_points = _offsets(coarse_radius, 5)
    # Score a finite subpixel/angle neighborhood first, then compile the
    # attractive cells into integer pivots. This orders the same native arcs
    # by the current palette instead of visiting thousands of poor pivots.
    # These poses never authorize input; actual arcs still pass _protect.
    ranked_cells = []
    w, h = r-l, b-t
    for angle in dict.fromkeys(seed[0] for seed in seeds):
        cells = []
        for dx, dy in itertools.product((-.15, -.10, -.05, 0., .05, .10, .15), repeat=2):
            guard()
            target = copy.deepcopy(pose)
            target['position'] = np.asarray(np.asarray(pose['position'], dtype=np.float32)+
                np.asarray([dx/w, -dy/h], dtype=np.float32), dtype=np.float32).tolist()
            target['rotation_degrees'] = float(np.float32(pose['rotation_degrees']+angle))
            # Actual target rules arrive through the caller-owned search context.
            rules = context.get('_refinement_rules')
            if rules is None:
                continue
            score = score_native_pose(context['session'], target, rules, check=guard)
            cells.append((predicted_quality(score, rules), target))
        refined = []
        for _, target in sorted(cells, key=lambda row: row[0])[:2]:
            for dx, dy in itertools.product((-.02, -.01, 0., .01, .02), repeat=2):
                guard()
                nearby = copy.deepcopy(target)
                nearby['position'] = np.asarray(np.asarray(target['position'], dtype=np.float32)+
                    np.asarray([dx/w, -dy/h], dtype=np.float32), dtype=np.float32).tolist()
                score = score_native_pose(context['session'], nearby, rules, check=guard)
                refined.append((predicted_quality(score, rules), nearby))
        ranked_cells.extend((quality, angle, target) for quality, target in sorted(refined,
                             key=lambda row: row[0])[:2])
    ranked_cells.sort(key=lambda cell: cell[0])
    directed = []
    for _, angle, target in ranked_cells:
        for wanted, ra, rb in seeds:
            if wanted != angle:
                continue
            compiled = event(anchor, rb, 1)
            delta = compiled[2]
            radians = float(np.float32(np.float32(delta)*np.float32(math.pi/180)))
            c, s = math.cos(radians), math.sin(radians)
            matrix = np.array([[c, -s], [s, c]])
            pivot_matrix = np.eye(2)-matrix
            if abs(np.linalg.det(pivot_matrix)) < 1e-12:
                continue
            center = np.linalg.solve(pivot_matrix,
                np.asarray(target['position'])-matrix@np.asarray(first_endpoints[ra]['position']))
            point = geometry.normalized_to_physical(center+.5)
            dx, dy = point[0]-anchor[0], point[1]-anchor[1]
            if max(abs(dx), abs(dy)) <= coarse_radius:
                directed.append(((dx, dy), (wanted, ra, rb)))
    def proposals(points, selected, stage):
        for dx, dy in points:
            for wanted, ra, rb in selected:
                guard()
                key = (ra, rb, dx, dy)
                if key in seen:
                    continue
                seen.add(key)
                second = (anchor[0]+dx, anchor[1]+dy)
                compiled = event(second, rb, 1)
                if compiled is None:
                    continue
                first = event(anchor, ra, -1)
                endpoint = apply_compiled(first_endpoints[ra], compiled)
                yield stage, [first[0], compiled[0]], endpoint
    for point, seed in directed:
        for ox, oy in _offsets(1):
            proposal = (point[0]+ox, point[1]+oy)
            if max(abs(v) for v in proposal) <= coarse_radius:
                yield from proposals([proposal], [seed], 'directed_rotation_pairs')
    # Interleave fine rings and the original coarse pivots so additional fine
    # coverage cannot starve a useful previously supported 10-pixel pivot move.
    for ring in range(fine_radius+1):
        fine = (point for point in fine_points if max(abs(v) for v in point) == ring)
        yield from proposals(fine, seeds, 'fine_rotation_pairs')
        if ring % 2 == 0:
            coarse_ring = ring//2*5
            coarse = (point for point in coarse_points
                      if max(abs(v) for v in point) == coarse_ring)
            yield from proposals(coarse, [seed for seed in seeds if abs(seed[0]) >= .02],
                                 'coarse_rotation_pairs')
    remaining = (point for point in coarse_points
                 if max(abs(v) for v in point) > fine_radius//2*5)
    yield from proposals(remaining, [seed for seed in seeds if abs(seed[0]) >= .02],
                         'coarse_rotation_pairs')


def _local_routes(context, radius_pixels, guard):
    """Geometry-only compatibility iterator for bounded offline investigations."""
    zero = dict(position=[0., 0.], scale=1., rotation_degrees=0.)
    for _, route, _ in _local_proposals(context, zero, radius_pixels, guard):
        yield route


def find_refinement(context, checkpoint, rules, *, deadline, clock=time.monotonic,
                    check=lambda: None, excluded=(), radius_pixels=5,
                    stats=None, progress=None):
    """Return one strict improvement with a complete return for every prefix."""
    from .same_session_dye_planner import _checked_checkpoint, normalize_target_rules
    guard = _guard(deadline, clock, check)
    stats = stats if isinstance(stats, dict) else {}
    stats.update(checked_routes=0, predicted_improvements=0, audited_candidates=0,
                 return_checked=0, deadline_reached=False, family_exhausted=False,
                 protected_candidate_found=False, stage='initial',
                 candidate_polish_seconds=.75, finite_candidate_upper_bound=32768)
    progress = progress if callable(progress) else (lambda update: None)
    if type(radius_pixels) is not int or not 1 <= radius_pixels <= 8:
        raise ValueError('Integer local radius must be one to eight pixels')
    best = None
    best_key = None
    polish_until = None
    try:
        guard()
        _checked_checkpoint(context, checkpoint)
        rules = normalize_target_rules(rules)
        context = dict(context, _refinement_rules=rules)
        baseline = observed_quality(checkpoint['client_hex'], rules)
        if not baseline[0]:
            return None
        blocked = {item if isinstance(item, str) else json.dumps(item, sort_keys=True)
                   for item in excluded}
        exhausted = True
        for index, (stage, route, endpoint) in enumerate(
                _local_proposals(context, checkpoint['pose'], radius_pixels, guard)):
            if (polish_until is not None and clock() >= polish_until and
                    stage != 'directed_rotation_pairs'):
                exhausted = False
                break
            if json.dumps(route, sort_keys=True) in blocked:
                continue
            if stage != stats['stage'] or stats['checked_routes'] % 128 == 0:
                stats['stage'] = stage
                progress(dict(stage=stage, checked_routes=stats['checked_routes'],
                              deadline_reached=False, family_exhausted=False))
            stats['checked_routes'] += 1
            prediction = score_native_pose(context['session'], endpoint, rules, check=guard)
            quality = predicted_quality(prediction, rules)
            if quality < baseline:
                stats['predicted_improvements'] += 1
            if quality >= baseline or (best_key is not None and quality >= best_key):
                continue
            row = dict(input_route=route, final_pose=endpoint, prediction=prediction,
                       needed=_needed(route, 3., .5), source='protected_local_'+stage)
            stats['audited_candidates'] += 1
            stats['stage'] = 'return_protection'
            progress(dict(stage='return_protection', checked_routes=stats['checked_routes'],
                          audited_candidates=stats['audited_candidates'],
                          return_checked=stats['return_checked'], family_exhausted=False,
                          deadline_reached=False))
            # The fast event score never authorizes input. This independently
            # replays the real descriptors and completes every prefix return.
            protected = _protect(context, checkpoint, rules, row, baseline, guard, stats)
            if protected is None:
                continue
            best, best_key = protected, quality
            stats.update(protected_candidate_found=True,
                         best_prediction=dict(colors=prediction['colors'],
                             predicted_accepted=prediction['predicted_accepted'],
                             deltas=prediction['deltas']))
            if prediction['predicted_accepted']:
                exhausted = False
                break
            if polish_until is None:
                polish_until = min(deadline, clock()+.75)
        stats['family_exhausted'] = exhausted
    except _Expired:
        stats['deadline_reached'] = True
    stats['stage'] = 'complete' if best is not None or stats['family_exhausted'] else 'deadline'
    progress(dict(stage=stats['stage'], checked_routes=stats['checked_routes'],
                  audited_candidates=stats['audited_candidates'],
                  return_checked=stats['return_checked'],
                  deadline_reached=stats['deadline_reached'],
                  family_exhausted=stats['family_exhausted'],
                  protected_candidate_found=best is not None))
    return best


def find_recovery(context, actual_checkpoint, baseline_checkpoint, rules, *, deadline,
                  clock=time.monotonic, check=lambda: None, radius_pixels=8,
                  preferred_routes=()):
    """Replay nearby returns from measured feedback; retain only anchor-or-better.

    Prepared routes are attempted first. Corrections are a bounded integer
    translation and nearby last-pivot changes, never a global pose search.
    """
    from .same_session_dye_planner import (_checked_checkpoint, normalize_target_rules,
                                         audit_candidate_endpoint, _research_route_allowed)
    guard = _guard(deadline, clock, check)
    if type(radius_pixels) is not int or not 1 <= radius_pixels <= 8:
        raise ValueError('Integer recovery radius must be one to eight pixels')
    try:
        guard()
        _checked_checkpoint(context, actual_checkpoint)
        _checked_checkpoint(context, baseline_checkpoint)
        rules = normalize_target_rules(rules)
        baseline = observed_quality(baseline_checkpoint['client_hex'], rules)
        geometry, settings = _geometry(context)
        l, t, r, b = geometry.board
        seen = set()
        def attempt(route):
            guard()
            signature = json.dumps(route, sort_keys=True)
            if signature in seen or len(route) > 4 or not _research_route_allowed(route, context['board']):
                return None
            seen.add(signature)
            row = _row(context, actual_checkpoint, rules, route, guard, 'measured_local_return')
            quality = predicted_quality(row['prediction'], rules)
            if quality > baseline:
                return None
            row = audit_candidate_endpoint(context, actual_checkpoint, rules, row, check=guard)
            guard()
            row.update(recovery_quality=quality, baseline_quality=baseline, ready_for_input=False)
            return row
        row = attempt([])
        if row is not None:
            return row
        routes = [copy.deepcopy(route) for route in preferred_routes]
        routes.append([])
        for route in routes:
            row = attempt(route)
            if row is not None:
                return row
            if len(route) >= 4 or not _research_route_allowed(route, context['board']):
                continue
            endpoint = _row(context, actual_checkpoint, rules, route, guard, 'return_residual')['final_pose']
            target = baseline_checkpoint['pose']['position']
            center = (round((target[0]-endpoint['position'][0])*(r-l)),
                      round((endpoint['position'][1]-target[1])*(b-t)))
            for ox, oy in _offsets(2):
                dx, dy = center[0]+ox, center[1]+oy
                if not (dx or dy) or max(abs(dx), abs(dy)) > radius_pixels:
                    continue
                drag = native_drag_gesture(geometry, settings, dx, dy).record()
                # Real translation residuals can be on the input lattice before
                # an inverse rotation and between lattice points afterwards.
                for corrected in ([*route, drag], [drag, *route]):
                    row = attempt(corrected)
                    if row is not None:
                        return row
            if route and route[-1]['kind'] == 'rotate':
                for dx, dy in _offsets(radius_pixels):
                    changed = copy.deepcopy(route)
                    gesture = changed[-1]
                    gesture['points'] = [(p[0]+dx, p[1]+dy) for p in gesture['points']]
                    row = attempt(changed)
                    if row is not None:
                        return row
    except _Expired:
        pass
    return None
