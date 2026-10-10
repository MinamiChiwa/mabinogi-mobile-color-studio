"""CPU shortlist followed by modeled action endpoints under one search budget."""
import math
import time
from native_palette_search import search_pose_grid
from native_palette_action_search import search_native_actions


def search_native_pipeline(session, grid, reference, board, markers, rules, *,
                           now, deadline, shortlist=100, top_k=10, time_budget_seconds=10.,
                           max_coarse_candidates=10000, action_reserve_seconds=None,
                           clock=time.monotonic, check=lambda: None):
    if type(shortlist) is not int or not 1 <= shortlist <= 1000:
        raise ValueError('Shortlist must be in [1,1000]')
    if not all(math.isfinite(v) for v in (now, deadline, time_budget_seconds)) or time_budget_seconds <= 0:
        raise ValueError('Invalid search timing')
    if action_reserve_seconds is not None and (not math.isfinite(action_reserve_seconds) or action_reserve_seconds <= 0 or action_reserve_seconds >= time_budget_seconds):
        raise ValueError('Action reserve must be positive and below search budget')
    start = clock()
    budget = min(time_budget_seconds, max(0., deadline - now))
    check()
    if budget <= 0:
        return dict(coarse=None, actions=None, stop_reason='search_deadline', elapsed_seconds=0.)
    reserve = budget * .3 if action_reserve_seconds is None else min(action_reserve_seconds, budget * .9)
    coarse = search_pose_grid(session, grid, rules, max_candidates=max_coarse_candidates,
                              top_k=shortlist, time_budget_seconds=budget - reserve, clock=clock, check=check)
    check()
    elapsed = max(0., clock() - start)
    remaining = budget - elapsed
    actions = None
    reason = 'no_shortlisted_candidates'
    if remaining <= 0:
        reason = 'search_deadline'
    elif coarse['candidates']:
        actions = search_native_actions(session, (r['native_pose'] for r in coarse['candidates']),
                                         reference, board, markers, rules, now=now + elapsed,
                                         deadline=deadline, max_candidates=shortlist, top_k=top_k,
                                         time_budget_seconds=remaining, clock=clock, check=check)
        reason = actions['stop_reason']
    return dict(coarse=coarse, actions=actions, stop_reason=reason,
                action_reserve_seconds=reserve,
                elapsed_seconds=max(0., clock() - start),
                optimality='CPU shortlist heuristic; may omit better modeled endpoints',
                execution_verified=False, game_response_verified=False)
