"""Small, live-adapter agnostic helpers for HEX feedback search.

The atlas prediction is only a starting point.  The game remains the source
of truth at the end of a move, so a local search must compare *stable* game
HEX readings and retain the best reading seen so far.  This module contains
the value-level pieces of that protocol.  It deliberately does not send
input or perform image registration; callers can use it from either the
atlas executor or an offline simulation.

The adapter used by :func:`stable_hex_read` is intentionally tiny:
``check()``, ``capture()``, ``read_codes(frame)`` and ``pause(seconds)``.
The optional ``check`` callback and deadline make the helper safe to use in a
countdown workflow without coupling it to ``atlas_execution``.
"""

from dataclasses import dataclass
import math
import time

import numpy as np

from hex_refinement import score_codes
from vision import normalize_hex


class HexFeedbackError(RuntimeError):
    """Base error for a failed feedback observation."""


class UnstableHexRead(HexFeedbackError):
    """The two reads around one pose did not agree."""


class SearchDeadlineExceeded(HexFeedbackError):
    """The caller's observation deadline elapsed before a read completed."""


@dataclass(frozen=True)
class NeighborhoodLimits:
    """Bounds for generating an integer/subpixel local pose neighborhood.

    ``steps`` are offsets in the caller's pose coordinates.  They are kept as
    floats because an adapter may measure subpixel image motion even though a
    physical mouse command is quantized.  Axis and diagonal offsets are
    generated at each step, deduplicated, and clipped to ``radius``.
    """

    steps: tuple = (1.0, 0.5)
    radius: float = 1.5
    include_diagonals: bool = True

    def __post_init__(self):
        if not self.steps:
            raise ValueError("At least one neighborhood step is required")
        values = tuple(float(value) for value in self.steps)
        if any(not math.isfinite(value) or value <= 0 for value in values):
            raise ValueError("Neighborhood steps must be finite and positive")
        if not math.isfinite(float(self.radius)) or float(self.radius) <= 0:
            raise ValueError("Neighborhood radius must be finite and positive")


def _guard(*, check=None, clock=time.monotonic, deadline=None):
    """Run an adapter guard and enforce an optional monotonic deadline."""

    if check is not None:
        check()
    if deadline is not None:
        try:
            expired = clock() >= float(deadline)
        except (TypeError, ValueError):
            raise ValueError("HEX feedback deadline must be finite")
        if not math.isfinite(float(deadline)):
            raise ValueError("HEX feedback deadline must be finite")
        if expired:
            raise SearchDeadlineExceeded("HEX feedback observation deadline expired")


def _canonical_codes(codes, rules):
    """Normalize OCR HEX values while preserving disabled-region values."""

    if len(codes) != len(rules):
        raise UnstableHexRead("HEX reading does not contain all configured regions")
    normalized = []
    for index, (code, rule) in enumerate(zip(codes, rules)):
        # Disabled cards are outside the objective.  OCR may return an empty
        # string or arbitrary UI text there, so discard that field rather than
        # allowing it to abort an otherwise valid three-region observation.
        if not rule.get("enabled", True):
            normalized.append(None)
            continue
        if code is None:
            normalized.append(None)
            continue
        try:
            normalized.append(normalize_hex(code))
        except (TypeError, ValueError) as exc:
            raise UnstableHexRead(
                "Invalid HEX reading for region %d: %s" % (index + 1, exc)
            ) from exc
    return tuple(normalized)


def stable_hex_read(adapter, rules, *, frame=None, pause=0.2,
                     check=None, clock=time.monotonic, deadline=None):
    """Read game HEX twice and return a canonical, stable observation.

    The first frame may be supplied when a caller has just completed a motion
    and already owns that capture.  The second frame is always captured after
    ``pause`` so callers never mistake a transient OCR result for a settled
    colour.  Only enabled regions participate in the equality check; disabled
    cards are allowed to be unreadable.  An enabled ``None`` is still a hard
    failure, because a local optimizer must never score missing feedback as a
    good result.

    The return value is a dictionary rather than a live object so it can be
    written directly into execution diagnostics and compared by tests.
    """

    if not math.isfinite(float(pause)) or float(pause) < 0:
        raise ValueError("HEX feedback pause must be finite and non-negative")
    _guard(check=check or getattr(adapter, "check", None), clock=clock,
           deadline=deadline)
    first_frame = frame if frame is not None else adapter.capture()
    _guard(check=check or getattr(adapter, "check", None), clock=clock,
           deadline=deadline)
    first = _canonical_codes(adapter.read_codes(first_frame), rules)
    if any(rule.get("enabled", True) and first[index] is None
           for index, rule in enumerate(rules)):
        raise UnstableHexRead("Enabled region HEX could not be read")
    _guard(check=check or getattr(adapter, "check", None), clock=clock,
           deadline=deadline)
    adapter.pause(float(pause))
    _guard(check=check or getattr(adapter, "check", None), clock=clock,
           deadline=deadline)
    second_frame = adapter.capture()
    _guard(check=check or getattr(adapter, "check", None), clock=clock,
           deadline=deadline)
    second = _canonical_codes(adapter.read_codes(second_frame), rules)
    _guard(check=check or getattr(adapter, "check", None), clock=clock,
           deadline=deadline)
    for index, rule in enumerate(rules):
        if rule.get("enabled", True) and first[index] != second[index]:
            raise UnstableHexRead(
                "HEX changed between verification frames for region %d" % (index + 1)
            )
    return dict(codes=list(second), first_codes=list(first),
                first_frame=first_frame, second_frame=second_frame,
                stable=True)


def neighborhood_offsets(limits=None):
    """Return deterministic, deduplicated local offsets for measured search.

    Axis moves are emitted before diagonals at each step.  This gives callers
    a cheap four-neighbour search first while still allowing a diagonal one
    pixel correction when all three regions need it.  The origin is omitted.
    """

    limits = limits or NeighborhoodLimits()
    if not isinstance(limits, NeighborhoodLimits):
        raise TypeError("limits must be NeighborhoodLimits")
    radius = float(limits.radius)
    directions = ((1, 0), (-1, 0), (0, 1), (0, -1))
    if limits.include_diagonals:
        directions += ((1, 1), (1, -1), (-1, 1), (-1, -1))
    result = []
    seen = set()
    for step in limits.steps:
        value = float(step)
        for dx, dy in directions:
            offset = np.asarray((dx * value, dy * value), dtype=float)
            if float(np.linalg.norm(offset)) > radius + 1e-12:
                continue
            key = tuple(np.round(offset, 9))
            if key in seen:
                continue
            seen.add(key)
            result.append(offset)
    return tuple(result)


def candidate_poses(center, limits=None):
    """Yield absolute poses around ``center`` in neighborhood order."""

    point = np.asarray(center, dtype=float)
    if point.shape != (2,) or not np.isfinite(point).all():
        raise ValueError("HEX search center must be a finite two-dimensional pose")
    return tuple(point + offset for offset in neighborhood_offsets(limits))


def score_observation(codes, rules, *, pose=None, frames=None):
    """Score one stable three-region reading using the shared rules.

    ``score_codes`` is the same ΔE/exact/tolerance implementation used by the
    existing refinement prototype.  The additional ``score_key`` is a plain
    tuple, suitable for ``min`` and JSON diagnostics, and makes the ranking
    explicit to callers retaining a global best.
    """

    canonical = _canonical_codes(codes, rules)
    scored = score_codes(list(canonical), rules)
    row = dict(scored, codes=list(canonical), pose=None if pose is None else
               np.asarray(pose, dtype=float).tolist())
    if frames is not None:
        row["frames"] = frames
    row["score_key"] = tuple(scored["rank"])
    return row


def retain_best(best, candidate):
    """Return the lower-error observation, preserving the historical best.

    A strict comparison intentionally keeps the earlier sample on ties.  This
    avoids unnecessary return moves when two adjacent poses produce the same
    HEX and makes the result deterministic across adapters.
    """

    if candidate is None:
        return best
    if best is None:
        return candidate
    candidate_key = tuple(candidate.get("score_key", candidate.get("rank", ())))
    best_key = tuple(best.get("score_key", best.get("rank", ())))
    return candidate if candidate_key < best_key else best


def rank_observations(observations):
    """Return observations ordered by the same key used by ``retain_best``."""

    return tuple(sorted(observations,
                        key=lambda row: tuple(row.get("score_key", row.get("rank", ())))))


__all__ = [
    "HexFeedbackError", "UnstableHexRead", "SearchDeadlineExceeded",
    "NeighborhoodLimits", "stable_hex_read", "neighborhood_offsets",
    "candidate_poses", "score_observation", "retain_best",
    "rank_observations",
]
