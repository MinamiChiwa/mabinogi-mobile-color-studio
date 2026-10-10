"""Bounded offline ranking of modeled action endpoints, never live execution."""
from dye_regions import validate_region_rules
import math
import time
import numpy as np
from native_palette_actions import assess_native_action


def search_native_actions(session, poses, reference, board, markers, rules, *,
                          now, deadline, max_candidates=10000, top_k=10,
                          time_budget_seconds=10., clock=time.monotonic, check=lambda: None):
    """Compile finite proposals and rank only budget-allowed planned endpoints.

    ``now``/``deadline`` use the caller's execution clock. Search duration is
    deducted from that budget. A compiler invocation is bounded by its own
    step limit; time checks surround it but cannot preempt it mid-function.
    """
    if type(max_candidates) is not int or not 1 <= max_candidates <= 100000:
        raise ValueError('Candidate limit must be in [1,100000]')
    if type(top_k) is not int or not 1 <= top_k <= 1000:
        raise ValueError('Invalid top_k')
    if not all(math.isfinite(v) for v in (now, deadline, time_budget_seconds)) or time_budget_seconds <= 0:
        raise ValueError('Finite clocks and positive search budget required')
    validate_region_rules(session, rules)
    start = clock()
    end = start + min(time_budget_seconds, max(0., deadline - now))
    endpoints = {}
    evaluated = rejected = missing = duplicates = 0
    stop_reason = 'candidates_exhausted'

    class Expired(Exception):
        pass

    def guard():
        check()
        if clock() >= end:
            raise Expired()

    def ranking(row):
        return (*row['planned_prediction']['rank'], row['budget'].get('needed', math.inf), row['candidate_index'])

    for index, pose in enumerate(poses):
        check()
        if evaluated >= max_candidates:
            stop_reason = 'candidate_limit'
            break
        try:
            guard()
            row = assess_native_action(session, pose, reference, board, markers, rules,
                                       now=now + max(0., clock() - start), deadline=deadline, check=guard)
            guard()
        except Expired:
            stop_reason = 'deadline'
            break
        evaluated += 1
        row['candidate_index'] = index
        if not row['plan_allowed']:
            rejected += 1
            continue
        if row['planned_prediction'] is None:
            missing += 1
            continue
        # Exact float64 matrix key avoids merging near endpoints whose RGB may differ.
        matrix = np.asarray(row['budget']['planned_pose'], dtype=np.float64)
        if matrix.shape != (2, 3) or not np.isfinite(matrix).all():
            raise ValueError('Invalid compiler endpoint')
        key = tuple(float(v) for v in matrix.ravel())
        previous = endpoints.get(key)
        if previous is not None:
            duplicates += 1
        if previous is None or ranking(row) < ranking(previous):
            endpoints[key] = row
    ordered = sorted(endpoints.values(), key=ranking)
    check()
    elapsed = max(0., clock() - start)
    remaining = max(0., deadline - now - elapsed)
    usable = [row for row in ordered if row['budget'].get('needed', math.inf) <= remaining]
    for row in usable:
        row['budget'] = dict(row['budget'], remaining=remaining)
    rows = usable[:top_k]
    return dict(candidates=rows, evaluated=evaluated, unique_endpoints=len(endpoints),
                duplicate_endpoints=duplicates, rejected_budget=rejected, missing_endpoint=missing,
                expired_after_search=len(ordered) - len(usable),
                planned_exact_count=sum(bool(row['planned_predicted_accepted']) for row in endpoints.values()),
                stop_reason=stop_reason, complete=stop_reason == 'candidates_exhausted',
                elapsed_seconds=elapsed, execution_seconds_remaining=remaining, capture_id=session['capture_id'],
                ranking_source='planned_endpoint_hex_then_action_cost',
                game_response_verified=False, execution_verified=False,
                optimality='best_in_evaluated_modeled_endpoints_only')
