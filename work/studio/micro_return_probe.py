"""Offline-only, injected controller for one X and one Y micro-return round.

There is deliberately no CLI or live input adapter. The adapter provides
check/context/marker_points/capture(name)/motion/read_codes/pause/release and
wheel(notch, anchor, *, deadline, guard). A future wheel implementation MUST
invoke guard at its final input boundary, including after moving the cursor.
check must enforce reliable countdown, focus, geometry and stop conditions.
capture must preserve named original images; matrix and marker coordinates
must agree. The caller passes the existing shared workflow deadline, never
a fresh sixty-second allowance. Timing reserves are uncalibrated estimates.
"""
from dataclasses import dataclass
import math
import re
import time
import numpy as np
from atlas_execution import checked_translation


@dataclass(frozen=True)
class ReturnLimits:
    stage_seconds: float = 25.
    pose_tolerance: float = .035
    minimum_motion: float = .005
    maximum_motion: float = 1.
    forward_seconds: float = 5.
    return_seconds: float = 3.
    verify_seconds: float = 4.
    between_notches: float = .035
    settle_seconds: float = .12
    between_reads: float = .2

    def __post_init__(self):
        if any(not math.isfinite(v) or v <= 0 for v in vars(self).values()):
            raise ValueError('Return limits must be finite and positive')
        if self.stage_seconds > 25 or self.minimum_motion >= self.maximum_motion:
            raise ValueError('Invalid stage or motion limits')


def strict_codes(values):
    """Require three already reliable OCR results; do not repair characters."""
    if not isinstance(values, (list, tuple)) or len(values) != 3:
        raise RuntimeError('Three reliable game HEX readings are required')
    if any(not isinstance(v, str) or re.fullmatch(r'#[0-9a-fA-F]{6}', v) is None for v in values):
        raise RuntimeError('Strict game HEX verification failed')
    return [v.upper() for v in values]


def run_micro_return(adapter, anchors, deadline, *, clock=time.monotonic, limits=None):
    """Request swapped-anchor returns; verify images and HEX, never retry.

    anchors maps x/y to two board-safe zoom anchors in capture coordinates.
    The adapter is responsible for bounds checks at the actual input boundary.
    Guard failure invalidates current state and never triggers compensating
    input. Historical observations, partial commands and timing survive failure.
    """
    limits = limits or ReturnLimits()
    if not math.isfinite(deadline):
        raise ValueError('Shared deadline must be finite')
    started = clock()
    effective_deadline = min(deadline, started + limits.stage_seconds)
    records = [dict(kind='micro_return_plan', shared_deadline=deadline,
                    deadline=effective_deadline, limits=vars(limits).copy(),
                    max_notches=8, live_validated=False)]
    phase = 'setup'
    context = None
    baseline = None
    current = None
    completed = []
    observations = []
    attempted = 0
    finished = 0
    failure = None
    reason = 'not_started'

    def guard():
        adapter.check()
        if context is not None and adapter.context() != context:
            raise RuntimeError('Session geometry changed')
        if clock() >= effective_deadline:
            raise RuntimeError('Micro-return deadline expired')

    def timed(operation, callback, **details):
        guard()
        event = dict(kind='micro_return_operation', phase=phase, operation=operation,
                     started=clock(), status='started', **details)
        records.append(event)
        try:
            value = callback()
            event['status'] = 'completed'
            return value
        except Exception as exc:
            event.update(status='failed', error=str(exc))
            raise
        finally:
            event['seconds'] = clock() - event['started']

    def pause(seconds):
        timed('wait', lambda: adapter.pause(seconds), requested_seconds=seconds)
        guard()

    def capture(name):
        frame = timed('capture', lambda: adapter.capture(name), frame=name)
        guard()
        return frame

    def read(frame, name):
        raw = timed('ocr', lambda: adapter.read_codes(frame), frame=name)
        records[-1]['codes'] = raw
        guard()
        return strict_codes(raw)

    def displacement(frame, name):
        motion = timed('registration', lambda: adapter.motion(reference, frame),
                       reference='baseline_0', frame=name)
        record = dict(kind='micro_return_motion', phase=phase, frame=name,
                      reference='baseline_0', motion=motion)
        records.append(record)
        guard()
        checked_translation(motion)
        if not all(math.isfinite(float(motion.get(k, default)))
                   for k, default in (('scale', 1), ('angle', 0))):
            raise RuntimeError('Nonfinite registration metadata')
        matrix = np.asarray(motion['matrix'], float)
        deltas = points @ (matrix[:, :2] - np.eye(2)).T + matrix[:, 2]
        mean = deltas.mean(axis=0)
        residual = float(np.max(np.linalg.norm(deltas - mean, axis=1)))
        record.update(point_displacements=deltas.tolist(), mean_displacement=mean.tolist(),
                      maximum_translation_residual=residual)
        if residual > limits.pose_tolerance:
            raise RuntimeError('Affine drift exceeds the three-marker tolerance')
        return deltas

    def observe(name, initial=None):
        nonlocal current
        current = None
        first = initial if initial is not None else capture(name + '_0')
        first_delta = displacement(first, name + '_0')
        a = read(first, name + '_0')
        pause(limits.between_reads)
        second = capture(name + '_1')
        second_delta = displacement(second, name + '_1')
        b = read(second, name + '_1')
        stable = bool(np.max(np.linalg.norm(second_delta - first_delta, axis=1)) <= limits.pose_tolerance)
        row = dict(phase=phase, frames=[name + '_0', name + '_1'], colors=[a, b],
                   point_displacements=[first_delta.tolist(), second_delta.tolist()],
                   geometry_stable=stable, hex_stable=a == b)
        observations.append(row)
        if not stable:
            raise RuntimeError('Board moved during double HEX verification')
        if a != b:
            raise RuntimeError('Game HEX changed between verification frames')
        current = row
        return row

    def at_baseline(row):
        return (row is not None and baseline is not None and
                row['colors'][1] == baseline['colors'][1] and
                np.max(np.linalg.norm(np.asarray(row['point_displacements']), axis=2)) <= limits.pose_tolerance)

    def pair(axis, reverse):
        nonlocal current, attempted, finished
        a, b = validated_anchors[axis]
        if reverse:
            a, b = b, a
        for notch, anchor, wait in ((1, a, limits.between_notches), (-1, b, limits.settle_seconds)):
            guard()
            if attempted >= 8:
                raise RuntimeError('Micro-return notch limit reached')
            tail_reserve = limits.verify_seconds
            if not reverse:
                tail_reserve += limits.return_seconds + limits.verify_seconds
            input_deadline = effective_deadline - tail_reserve - wait

            def input_guard():
                guard()
                if clock() >= input_deadline:
                    raise RuntimeError('Insufficient reserve at wheel input boundary')

            input_guard()
            current = None
            attempted += 1
            timed('wheel', lambda: adapter.wheel(notch, anchor.copy(),
                                               deadline=input_deadline, guard=input_guard),
                  attempt=attempted, notch=notch, anchor=anchor.tolist(), reverse=reverse,
                  input_deadline=input_deadline, tail_reserve_seconds=tail_reserve)
            finished += 1
            guard()
            pause(wait)

    try:
        guard()
        context = adapter.context()
        points = np.asarray(adapter.marker_points(), float)
        if points.shape != (3, 2) or not np.isfinite(points).all():
            raise ValueError('Three finite marker points in motion coordinates are required')
        validated_anchors = {}
        for axis, index in (('x', 0), ('y', 1)):
            value = np.asarray(anchors[axis], float)
            if value.shape != (2, 2) or not np.isfinite(value).all():
                raise ValueError('Two finite anchors per axis are required')
            delta = value[1] - value[0]
            if not 8 <= delta[index] <= 24 or abs(delta[1-index]) > 1e-9:
                raise ValueError('Anchor separation must be 8 to 24 pixels along the named axis')
            validated_anchors[axis] = value
        records[0].update(marker_points=points.tolist(),
                          anchors={k: v.tolist() for k, v in validated_anchors.items()})
        guard()
        if effective_deadline - clock() < limits.verify_seconds:
            reason = 'insufficient_baseline_budget'
        else:
            phase = 'baseline'
            reference = capture('baseline_0')
            row = observe('baseline', reference)
            if np.max(np.linalg.norm(np.asarray(row['point_displacements']), axis=2)) > limits.pose_tolerance:
                raise RuntimeError('Baseline moved before verification')
            baseline = row
            reason = 'completed'
            for axis, index in (('x', 0), ('y', 1)):
                phase = axis + '_reserve'
                guard()
                reserve = limits.forward_seconds + limits.return_seconds + limits.verify_seconds
                if effective_deadline - clock() < reserve:
                    reason = 'insufficient_roundtrip_budget'
                    break
                phase = axis + '_forward'
                pair(axis, False)
                moved = observe(phase)
                for delta in np.asarray(moved['point_displacements']):
                    mean = delta.mean(axis=0)
                    if (abs(mean[index]) < limits.minimum_motion or
                            np.max(np.linalg.norm(delta, axis=1)) > limits.maximum_motion or
                            abs(mean[1-index]) > limits.pose_tolerance):
                        raise RuntimeError('No reliable bounded motion along the requested axis')
                phase = axis + '_return'
                guard()
                if effective_deadline - clock() < limits.return_seconds + limits.verify_seconds:
                    raise RuntimeError('Insufficient budget to request and verify return')
                pair(axis, True)
                restored = observe(phase)
                if not at_baseline(restored):
                    raise RuntimeError('Return did not reproduce baseline geometry and all three HEX')
                completed.append(axis)
            guard()
    except Exception as exc:
        reason, failure, current = 'stopped', str(exc), None
        records.append(dict(kind='micro_return_failure', phase=phase, error=failure, at=clock()))
    finally:
        release_started = clock()
        try:
            adapter.release()
            records.append(dict(kind='micro_return_release', status='completed',
                                seconds=clock() - release_started))
        except Exception as exc:
            release_error = str(exc)
            records.append(dict(kind='micro_return_release', status='failed', error=release_error,
                                seconds=clock() - release_started))
            reason, current = 'stopped', None
            failure = ((failure + '; ') if failure else '') + 'Release failed: ' + release_error
    # Release may consume time or change the guard context. Recheck without input.
    if current is not None:
        try:
            guard()
        except Exception as exc:
            reason, failure, current = 'stopped', str(exc), None
            records.append(dict(kind='micro_return_failure', phase='after_release', error=failure, at=clock()))
    returned = bool(at_baseline(current))
    return dict(reason=reason, error=failure, phase=phase, deadline=effective_deadline,
                elapsed=clock() - started, attempted_notches=attempted, completed_notches=finished,
                axes_completed=completed, baseline=baseline, current=current,
                current_verified=current is not None, baseline_verified_now=returned,
                returned_to_baseline=returned and bool(completed),
                protocol_passed=reason == 'completed' and completed == ['x', 'y'] and returned,
                live_validated=False, observations=observations, records=records)
