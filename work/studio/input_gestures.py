"""Pure, immutable client-pixel inputs shared by planning and Windows input.

Cursor geometry is deliberately distinct from measured texture response. The
arc extent below is diagnostic, not a calibrated game rotation prediction.
Repeated points retain their waits; removing them would change input cadence.
"""
from dataclasses import asdict, dataclass, replace
from functools import lru_cache
import math
import numpy as np


@dataclass(frozen=True)
class GestureTiming:
    before_down: float = .08
    after_down: float = .10
    point_interval: float = .018
    before_up: float = .08
    after_wheel: float = .10


@dataclass(frozen=True)
class PointerGesture:
    kind: str
    points: tuple
    right: bool = False
    absolute: bool = True
    wheel_steps: int = 0
    requested_angle: float = 0.
    arc_start: int = 0
    timing: GestureTiming = GestureTiming()

    @property
    def anchor(self):
        return self.points[0]

    @property
    def translation(self):
        return tuple(b-a for a, b in zip(self.points[0], self.points[-1]))

    @property
    def arc_degrees(self):
        if self.kind != 'rotate':
            return 0.
        vectors = np.asarray(self.points[self.arc_start:], float)-self.anchor
        angles = np.unwrap(np.arctan2(vectors[:, 1], vectors[:, 0]))
        return float(np.degrees(angles[-1]-angles[0]))

    @property
    def has_effect(self):
        """Whether the integer input has geometric effect, not proof of response."""
        if self.kind == 'wheel':
            return self.wheel_steps != 0
        if self.kind == 'rotate':
            return (len(set(self.points[self.arc_start:])) > 1 and
                    self.arc_degrees*self.requested_angle > 0)
        return len(set(self.points)) > 1

    @property
    def duration(self):
        if not self.has_effect:
            return 0.
        t = self.timing
        if self.kind == 'wheel':
            return abs(self.wheel_steps)*t.point_interval+t.after_wheel
        return t.before_down+t.after_down+(len(self.points)-1)*t.point_interval+t.before_up

    def record(self):
        data = asdict(self)
        data.update(schema=1, coordinate_space='physical_client_pixels',
                    input_seconds=self.duration, has_effect=self.has_effect)
        if self.kind == 'rotate':
            data.update(cursor_arc_degrees=self.arc_degrees,
                        response_model='unverified_cursor_geometry')
        return data


def _board(board):
    values = tuple(float(v) for v in board)
    if len(values) != 4 or not all(math.isfinite(v) for v in values):
        raise ValueError('Invalid gesture board')
    l, t, r, b = values
    if r-l < 24 or b-t < 24:
        raise ValueError('Board too small for mouse gestures')
    return values


def path_gesture(points, right=False, absolute=False):
    points = tuple(tuple(round(float(v)) for v in p) for p in points)
    if not points or any(len(p) != 2 for p in points):
        raise ValueError('Mouse path requires two-dimensional points')
    return PointerGesture('path', points, right=right, absolute=absolute)


def drag_gesture(board, dx, dy):
    l, t, r, b = _board(board)
    if not np.isfinite([dx, dy]).all():
        raise ValueError('Non-finite drag')
    # Preserve the established truncation and clipping at the input boundary.
    dx = int(np.clip(dx, -(r-l)*.65, (r-l)*.65))
    dy = int(np.clip(dy, -(b-t)*.65, (b-t)*.65))
    sx, sy = round((l+r-dx)/2), round((t+b-dy)/2)
    count = max(1, min(24, max(abs(dx), abs(dy))))
    points = tuple((round(sx+dx*i/count), round(sy+dy*i/count)) for i in range(count+1))
    return PointerGesture('drag', points)


@lru_cache(maxsize=512)
def _rotation_gesture(board, anchor, angle):
    l, t, r, b = board
    cx, cy = anchor
    best = None
    if not (l+8 < cx < r-8 and t+8 < cy < b-8):
        raise ValueError('旋转按下点距离色板边缘太近。')
    for base in range(0, 360, 15):
        angles = np.radians(base+np.linspace(0, angle, 49))
        vx, vy = np.cos(angles), np.sin(angles)
        limits = [min(r-l, b-t)*.8]
        for values, negative, positive in ((vx, cx-l-6, r-cx-6), (vy, cy-t-6, b-cy-6)):
            if np.any(values > 1e-6):
                limits.append(float(np.min(positive/values[values > 1e-6])))
            if np.any(values < -1e-6):
                limits.append(float(np.min(-negative/values[values < -1e-6])))
        radius = min(limits)
        if best is None or radius > best[0]:
            best = radius, base
    radius, base = best
    theta = math.radians(base)
    points = [(round(cx+radius*i/8*math.cos(theta)), round(cy+radius*i/8*math.sin(theta)))
              for i in range(9)]
    points += [(round(cx+radius*math.cos(math.radians(base+angle*i/24))),
                round(cy+radius*math.sin(math.radians(base+angle*i/24)))) for i in range(1, 25)]
    return PointerGesture('rotate', tuple(points), right=True,
                          requested_angle=angle, arc_start=8)


def rotation_gesture(board, angle, anchor=None):
    """Original dense arc, retained for historical replay and comparisons."""
    board = _board(board)
    l, t, r, b = board
    anchor = tuple(round(float(v)) for v in (anchor if anchor is not None else ((l+r)/2, (t+b)/2)))
    angle = float(angle)
    if not math.isfinite(angle):
        raise ValueError('Non-finite rotation')
    return _rotation_gesture(board, anchor, angle)


@lru_cache(maxsize=512)
def _grouped_rotation(original):
    count=len(original.points)-original.arc_start-1
    # Controlled in-game comparisons support grouping small cursor increments.
    # .5 degrees is a grouping target, not a minimum game response or bound.
    segments=min(count,max(1,math.ceil(abs(original.requested_angle)/.5)))
    boundaries={math.ceil(i*count/segments) for i in range(1,segments+1)}
    points=list(original.points[:original.arc_start+1])
    current=points[-1]
    for index in range(1,count+1):
        if index in boundaries:current=original.points[original.arc_start+index]
        points.append(current)
    return replace(original,points=tuple(points))


def grouped_rotation_gesture(board, angle, anchor=None):
    """Group arc updates; preserve pivot, endpoint, radial path and all waits.

    Only the sampled 701-pixel board conditions have live comparison evidence.
    Other conditions still require measured feedback. In particular an integer
    endpoint does not guarantee that an arbitrarily small arc has game effect.
    """
    return _grouped_rotation(rotation_gesture(board,angle,anchor))


def rotation_path(board, anchor, angle):
    """Compatibility helper; callers needing timing should use rotation_gesture."""
    return list(rotation_gesture(board, angle, anchor).points)


def wheel_gesture(board, steps, anchor=None):
    l, t, r, b = _board(board)
    if not math.isfinite(steps) or int(steps) != steps:
        raise ValueError('Wheel steps must be whole notches')
    point = tuple(round(float(v)) for v in (anchor if anchor is not None else ((l+r)/2, (t+b)/2)))
    if not (l < point[0] < r and t < point[1] < b):
        raise ValueError('缩放中心必须位于色板内。')
    count = min(32, abs(int(steps)))*(1 if steps > 0 else -1)
    return PointerGesture('wheel', (point,), wheel_steps=count)


def planned_gesture(kind, board, command, anchor=None):
    if kind == 'drag':
        return drag_gesture(board, *command)
    if kind == 'rotate':
        return grouped_rotation_gesture(board, command, anchor)
    if kind == 'wheel':
        return wheel_gesture(board, command, anchor)
    raise ValueError(f'Unknown gesture kind: {kind}')
