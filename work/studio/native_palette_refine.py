"""Bounded local multi-scale refinement over native normalized poses."""
import math
import time
import heapq
from dye_regions import validate_region_rules
from native_palette_scoring import _pose, score_native_pose


def _steps(values):
    result = tuple(float(value) for value in values)
    if not result or len(result) > 32 or any(not math.isfinite(v) or v <= 0 for v in result):
        raise ValueError('Refinement steps must be finite and positive')
    return result


def refine_native_poses(session, seeds, rules, *, translation_steps=(.01, .0025),
                        scale_steps=(.01,), rotation_steps=(1.,), max_candidates=10000,
                        top_k=10, time_budget_seconds=10., clock=time.monotonic,
                        check=lambda: None):
    """Refine each seed with origin, axes and diagonals at each explicit layer."""
    if not seeds or type(max_candidates) is not int or max_candidates < 1:
        raise ValueError('Seeds and positive candidate limit required')
    if type(top_k) is not int or not 1 <= top_k <= 1000:
        raise ValueError('Invalid top_k')
    if not math.isfinite(time_budget_seconds) or time_budget_seconds <= 0:
        raise ValueError('Positive finite time budget required')
    translation_steps = _steps(translation_steps)
    scale_steps = _steps(scale_steps)
    rotation_steps = _steps(rotation_steps)
    if len(seeds) > 1000:
        raise ValueError('At most 1000 seeds allowed')
    seeds = [_pose(seed) for seed in seeds]
    validate_region_rules(session, rules)
    start = clock()
    deadline = start + time_budget_seconds
    layers = max(len(translation_steps), len(scale_steps), len(rotation_steps))
    seen, retained = set(), []
    evaluated = 0
    layers_completed = 0
    stop_reason = 'refinement_exhausted'

    class Expired(Exception):
        pass

    def guard():
        check()
        if clock() >= deadline:
            raise Expired()

    def pose_key(pose):
        return tuple(round(float(v), 9) for v in (*pose['position'], pose['scale'], pose['rotation_degrees']))

    def neighbors(seed, layer):
        t = translation_steps[min(layer, len(translation_steps) - 1)]
        s = scale_steps[min(layer, len(scale_steps) - 1)]
        r = rotation_steps[min(layer, len(rotation_steps) - 1)]
        yield dict(seed)
        for dx, dy in ((t, 0), (-t, 0), (0, t), (0, -t), (t, t), (t, -t), (-t, t), (-t, -t)):
            yield dict(position=[seed['position'][0] + dx, seed['position'][1] + dy], scale=seed['scale'], rotation_degrees=seed['rotation_degrees'])
        for ds in (-s, s):
            if seed['scale'] + ds > 0:
                yield dict(position=list(seed['position']), scale=seed['scale'] + ds, rotation_degrees=seed['rotation_degrees'])
        for dr in (-r, r):
            yield dict(position=list(seed['position']), scale=seed['scale'], rotation_degrees=seed['rotation_degrees'] + dr)

    for layer in range(layers):
        try:
            for seed in seeds:
                for pose in neighbors(seed, layer):
                    guard()
                    pose = _pose(pose)
                    key = pose_key(pose)
                    if key in seen:
                        continue
                    seen.add(key)
                    if evaluated >= max_candidates:
                        stop_reason = 'candidate_limit'
                        raise Expired()
                    row = score_native_pose(session, pose, rules, check=guard)
                    guard()
                    row['refinement_layer'] = layer
                    row['candidate_index'] = evaluated
                    evaluated += 1
                    entry = (tuple(-float(v) for v in row['rank']), -row['candidate_index'], row)
                    if len(retained) < top_k:
                        heapq.heappush(retained, entry)
                    elif entry[:2] > retained[0][:2]:
                        heapq.heapreplace(retained, entry)
        except Expired:
            if stop_reason == 'refinement_exhausted':
                stop_reason = 'deadline'
            break
        layers_completed += 1
        # Keep the best prior centres even if deduplication skipped their origin.
        if retained:
            seeds = [row['native_pose'] for row in sorted((entry[2] for entry in retained), key=lambda row: row['rank'])[:max(1, min(8, top_k))]]
    rows = sorted((entry[2] for entry in retained), key=lambda row: (row['rank'], row['candidate_index']))
    return dict(candidates=rows, evaluated=evaluated, layers_evaluated=layers_completed,
                planned_candidates=None, complete=stop_reason == 'refinement_exhausted', stop_reason=stop_reason,
                elapsed_seconds=max(0., clock() - start), time_budget_seconds=time_budget_seconds,
                capture_id=session['capture_id'], input_reachability='unverified',
                optimality='best_retained_in_evaluated_local_layers_only')
