"""Bounded offline grid search of shared native dye poses.

Bounds and scale/angle choices are explicit caller inputs. Grid completion
means only that this discrete grid was scored, never global optimality or
mouse reachability. No UI, process inspection or input is performed.
"""
from dataclasses import dataclass
import math
import time
import heapq
import numpy as np
from dye_regions import validate_region_rules
from native_palette_scoring import score_native_pose


@dataclass(frozen=True)
class PoseGrid:
    x_bounds: tuple
    y_bounds: tuple
    x_count: int
    y_count: int
    scales: tuple
    rotations_degrees: tuple

    def __post_init__(self):
        for name in ('x_bounds', 'y_bounds'):
            bounds = tuple(float(v) for v in getattr(self, name))
            if len(bounds) != 2 or not all(math.isfinite(v) for v in bounds) or bounds[0] > bounds[1]:
                raise ValueError('Invalid position bounds')
            object.__setattr__(self, name, bounds)
        for count in (self.x_count, self.y_count):
            if type(count) is not int or not 1 <= count <= 10000:
                raise ValueError('Grid counts must be integers in [1,10000]')
        for name in ('scales', 'rotations_degrees'):
            values = tuple(float(v) for v in getattr(self, name))
            if not values or len(values) > 1000 or not all(math.isfinite(v) for v in values):
                raise ValueError('Finite scale/rotation samples required')
            if name == 'scales' and min(values) <= 0:
                raise ValueError('Scales must be positive')
            object.__setattr__(self, name, values)

    @property
    def count(self):
        return self.x_count * self.y_count * len(self.scales) * len(self.rotations_degrees)

    def poses(self):
        for scale in self.scales:
            for rotation in self.rotations_degrees:
                for y in np.linspace(*self.y_bounds, self.y_count):
                    for x in np.linspace(*self.x_bounds, self.x_count):
                        yield dict(position=[float(x), float(y)], scale=scale, rotation_degrees=rotation)


def search_pose_grid(session, grid, rules, *, max_candidates=10000, top_k=10,
                     time_budget_seconds=10., clock=time.monotonic, check=lambda: None):
    """Return the best predictions and explicit budget/coverage diagnostics."""
    if not isinstance(grid, PoseGrid):
        raise ValueError('PoseGrid required')
    if type(max_candidates) is not int or max_candidates < 1 or type(top_k) is not int or not 1 <= top_k <= 1000:
        raise ValueError('Invalid candidate/retention limit')
    if not math.isfinite(time_budget_seconds) or time_budget_seconds <= 0:
        raise ValueError('Positive finite time budget required')
    validate_region_rules(session, rules)
    start = clock()
    deadline = start + time_budget_seconds
    retained = []
    evaluated = accepted = 0
    reason = 'grid_exhausted'

    class Expired(Exception):
        pass

    def guard():
        check()
        if clock() >= deadline:
            raise Expired()

    for index, pose in enumerate(grid.poses()):
        check()
        if evaluated >= max_candidates:
            reason = 'candidate_limit'
            break
        try:
            guard()
            row = score_native_pose(session, pose, rules, check=guard)
            guard()
        except Expired:
            reason = 'deadline'
            break
        row['candidate_index'] = index
        evaluated += 1
        accepted += int(row['predicted_accepted'])
        # Negative rank puts the worst retained candidate at the heap root.
        entry = (tuple(-float(v) for v in row['rank']), -index, row)
        if len(retained) < top_k:
            heapq.heappush(retained, entry)
        elif entry[:2] > retained[0][:2]:
            heapq.heapreplace(retained, entry)
    rows = sorted((entry[2] for entry in retained), key=lambda row: (row['rank'], row['candidate_index']))
    return dict(candidates=rows, evaluated=evaluated, planned_candidates=grid.count,
                predicted_accepted_count=accepted, stop_reason=reason,
                grid_complete=evaluated == grid.count,
                elapsed_seconds=max(0., clock() - start), time_budget_seconds=time_budget_seconds,
                capture_id=session['capture_id'], input_reachability='unverified',
                optimality='best_retained_in_evaluated_discrete_grid_only')
