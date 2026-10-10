"""Local proposals ranked by freshly compiled endpoints under one budget."""
import math
import time
from native_palette_action_search import search_native_actions
from native_palette_pose import _size


def refine_action_endpoints(session, candidates, reference, board, markers, rules, *,
                            now, deadline, pixel_steps=(1., .5, .25),
                            angle_steps=(.1, .05, .025), scale_steps=(.001, .0005, .00025),
                            max_candidates=1000, top_k=5, time_budget_seconds=10.,
                            clock=time.monotonic, check=lambda: None):
    """Refine centers from predicted endpoints, preserving prior routes.

    All commands are recompiled from the same current reference. This does
    not assume the previous candidate was executed or build a chained route.
    """
    steps = [tuple(float(v) for v in values) for values in (pixel_steps, angle_steps, scale_steps)]
    if any(not values or len(values) > 16 or any(not math.isfinite(v) or v <= 0 for v in values) for values in steps):
        raise ValueError('Finite positive refinement steps required')
    if type(max_candidates) is not int or not 1 <= max_candidates <= 10000 or type(top_k) is not int or not 1 <= top_k <= 100:
        raise ValueError('Invalid retention/evaluation limits')
    if not all(math.isfinite(v) for v in (now, deadline, time_budget_seconds)) or time_budget_seconds <= 0:
        raise ValueError('Invalid timing')
    width, height = _size(board)
    for candidate in candidates:
        if candidate.get('capture_id') != session['capture_id']:
            raise ValueError('Candidate belongs to another capture')
    start = clock()
    end = start + min(time_budget_seconds, max(0., deadline - now))
    retained = list(candidates)
    evaluated = completed = 0
    reason = 'layers_exhausted'
    diagnostics = []
    for layer in range(max(map(len, steps))):
        check()
        remaining = end - clock()
        if remaining <= 0:
            reason = 'deadline'
            break
        if not retained:
            reason = 'no_candidates'
            break
        if evaluated >= max_candidates:
            reason = 'candidate_limit'
            break
        px, angle, scale = [v[min(layer, len(v) - 1)] for v in steps]
        proposals = []
        for row in retained[:top_k]:
            # Preserve the original proposal that produced this route as well as its endpoint.
            proposals.append(row['proposal_prediction']['native_pose'])
            center = row['planned_prediction']['native_pose']
            proposals.append(center)
            for dx, dy in ((px, 0), (-px, 0), (0, px), (0, -px), (px, px), (px, -px), (-px, px), (-px, -px)):
                proposals.append(dict(center, position=[center['position'][0] + dx / width,
                                                        center['position'][1] - dy / height]))
            for delta in (-angle, angle):
                proposals.append(dict(center, rotation_degrees=center['rotation_degrees'] + delta))
            for delta in (-scale, scale):
                if center['scale'] + delta > 0:
                    proposals.append(dict(center, scale=center['scale'] + delta))
        result = search_native_actions(session, proposals, reference, board, markers, rules,
                                        now=now + max(0., clock() - start), deadline=deadline,
                                        max_candidates=max_candidates - evaluated, top_k=top_k,
                                        time_budget_seconds=remaining, clock=clock, check=check)
        evaluated += result['evaluated']
        diagnostics.append({k: v for k, v in result.items() if k != 'candidates'})
        # Rank new routes together with the still-valid historical routes.
        elapsed = max(0., clock() - start)
        usable = [r for r in retained + result['candidates'] if r['budget']['needed'] <= deadline - now - elapsed]
        usable.sort(key=lambda r: (*r['planned_prediction']['rank'], r['budget']['needed']))
        unique = {}
        for row in usable:
            key = tuple(v for line in row['budget']['planned_pose'] for v in line)
            if key not in unique:
                unique[key] = row
        retained = list(unique.values())[:top_k]
        if result['stop_reason'] != 'candidates_exhausted':
            reason = result['stop_reason']
            break
        completed += 1
    check()
    elapsed = max(0., clock() - start)
    retained = [r for r in retained if r['budget']['needed'] <= deadline - now - elapsed]
    for row in retained:
        row['budget'] = dict(row['budget'], remaining=max(0., deadline - now - elapsed))
    return dict(candidates=retained, evaluated=evaluated, layers_completed=completed,
                stop_reason=reason, elapsed_seconds=elapsed, layers=diagnostics,
                execution_verified=False, game_response_verified=False,
                optimality='local proposals recompiled from reference; no global or live claim')
