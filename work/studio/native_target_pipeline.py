"""Offline target-seed, shortlist, endpoint and refinement stages, one budget."""
from dye_regions import validate_region_rules
import heapq
import itertools
import math
import time
from native_target_seeds import target_seed_poses
from native_palette_scoring import score_native_pose
from native_palette_action_search import search_native_actions
from native_action_refine import refine_action_endpoints
from native_palette_search import PoseGrid


def search_target_pipeline(session, grid, reference, board, markers, rules, *,
                           now, deadline, time_budget_seconds=12., shortlist=100, top_k=5,
                           seed_budget=None, coarse_budget=None, endpoint_budget=None,
                           pixels_per_region=16, subpixel_fractions=(0., .25, .5, .75),
                           seed_rotations=None, max_seeds=3000, max_coarse_candidates=10000,
                           max_refine_candidates=1000, refine=True,
                           clock=time.monotonic, check=lambda: None):
    """Heuristic offline pipeline; returned routes still need live validation.

    Stage budgets are caps, not independent deadline extensions. Unused stage
    time is available for the final refinement within the overall deadline.
    """
    if not isinstance(grid, PoseGrid):
        raise ValueError('PoseGrid required')
    validate_region_rules(session, rules)
    if not all(math.isfinite(v) for v in (now, deadline, time_budget_seconds)) or time_budget_seconds <= 0:
        raise ValueError('Invalid workflow timing')
    if type(shortlist) is not int or not 1 <= shortlist <= 1000 or type(top_k) is not int or not 1 <= top_k <= 100:
        raise ValueError('Invalid shortlist/retention count')
    for value in (max_seeds, max_coarse_candidates, max_refine_candidates):
        if type(value) is not int or not 1 <= value <= 100000:
            raise ValueError('Invalid stage candidate limit')
    caps = [time_budget_seconds * .35 if seed_budget is None else seed_budget,
            time_budget_seconds * .25 if coarse_budget is None else coarse_budget,
            time_budget_seconds * .2 if endpoint_budget is None else endpoint_budget]
    if not all(math.isfinite(v) and v > 0 for v in caps) or sum(caps) > time_budget_seconds + 1e-9:
        raise ValueError('Stage caps must fit total search budget')
    start = clock()
    end = start + min(time_budget_seconds, max(0., deadline - now))
    stages = dict(seed=None, coarse=None, endpoint=None, refinement=None)
    candidates = []
    reason = 'completed'

    class Expired(Exception):
        pass

    def guard():
        check()
        if clock() >= end:
            raise Expired()

    def cap(value):
        guard()
        return min(value, end - clock())

    try:
        stages['seed'] = target_seed_poses(session, rules, scales=grid.scales,
                                          rotations_degrees=grid.rotations_degrees if seed_rotations is None else seed_rotations,
                                          pixels_per_region=pixels_per_region, subpixel_fractions=subpixel_fractions,
                                          reference=reference, max_candidates=max_seeds,
                                          time_budget_seconds=cap(caps[0]), clock=clock, check=guard)
        guard()
        coarse_start = clock()
        coarse_end = coarse_start + cap(caps[1])
        retained, seen = [], set()
        evaluated = attempted = 0
        coarse_reason = 'candidates_exhausted'
        proposals = itertools.chain(stages['seed']['poses'], grid.poses())
        for pose in proposals:
            guard()
            if clock() >= coarse_end:
                coarse_reason = 'stage_deadline'
                break
            if attempted >= max_coarse_candidates:
                coarse_reason = 'candidate_limit'
                break
            attempted += 1
            key = tuple((*pose['position'], pose['scale'], pose['rotation_degrees']))
            if key in seen:
                continue
            seen.add(key)
            row = score_native_pose(session, pose, rules, check=guard)
            guard()
            entry = (tuple(-float(v) for v in row['rank']), -evaluated, row)
            evaluated += 1
            if len(retained) < shortlist:
                heapq.heappush(retained, entry)
            elif entry[:2] > retained[0][:2]:
                heapq.heapreplace(retained, entry)
        selected = sorted(retained, key=lambda entry: (entry[2]['rank'], -entry[1]))
        stages['coarse'] = dict(evaluated=evaluated, attempted=attempted, shortlisted=len(selected),
                                 planned_candidates=stages['seed']['generated'] + grid.count,
                                 stop_reason=coarse_reason, elapsed_seconds=clock() - coarse_start)
        if selected:
            stages['endpoint'] = search_native_actions(session, [entry[2]['native_pose'] for entry in selected],
                                                        reference, board, markers, rules,
                                                        now=now + clock() - start, deadline=deadline,
                                                        max_candidates=shortlist, top_k=top_k,
                                                        time_budget_seconds=cap(caps[2]), clock=clock, check=guard)
            candidates = stages['endpoint']['candidates']
        else:
            reason = 'no_shortlisted_candidates'
        if refine and candidates:
            stages['refinement'] = refine_action_endpoints(session, candidates, reference, board, markers, rules,
                                                            now=now + clock() - start, deadline=deadline,
                                                            pixel_steps=(1., .5, .25, .125, .0625),
                                                            angle_steps=(.1, .05, .025, .0125, .00625),
                                                            scale_steps=(.001, .0005, .00025, .000125, .0000625),
                                                            max_candidates=max_refine_candidates, top_k=top_k,
                                                            time_budget_seconds=cap(time_budget_seconds), clock=clock, check=guard)
            candidates = stages['refinement']['candidates']
        guard()
    except Expired:
        reason = 'deadline'
    check()
    elapsed = max(0., clock() - start)
    remaining = max(0., deadline - now - elapsed)
    candidates = [r for r in candidates if r['budget']['needed'] <= remaining]
    for row in candidates:
        row['budget'] = dict(row['budget'], remaining=remaining)
    return dict(candidates=candidates, stages=stages, stop_reason=reason,
                elapsed_seconds=elapsed, search_budget_seconds=min(time_budget_seconds, max(0., deadline - now)),
                stage_caps_seconds=caps, execution_seconds_remaining=remaining,
                capture_id=session['capture_id'], execution_verified=False, game_response_verified=False,
                optimality='finite target-seed/grid shortlist and local modeled endpoints only')
