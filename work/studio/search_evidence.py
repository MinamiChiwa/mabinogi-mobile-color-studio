"""Per-round evidence and conservative costs; never sends input or guesses HEX."""
from contextlib import contextmanager
from copy import deepcopy
from functools import wraps
import math
import time

import numpy as np

from vision import accepted, error, normalize_hex

DEFAULT_SECONDS = {'capture': .25, 'registration': .8, 'ocr': 2.5, 'search': .5,
                   'binding': .5, 'input': .6, 'return': 1.8, 'verification': 3.5,
                   'storage': .2, 'recognition': .5, 'settling': .2}


def timed(stage):
    """Instrument live adapter methods; deterministic adapters remain unchanged."""
    def decorate(function):
        @wraps(function)
        def wrapped(self, *args, **kwargs):
            evidence = getattr(self, 'evidence', None)
            if not isinstance(evidence, RoundEvidence):
                return function(self, *args, **kwargs)
            name = getattr(self, 'input_stage', 'input') if stage == 'input' else stage
            with evidence.measure(name):
                return function(self, *args, **kwargs)
        return wrapped
    return decorate


def _seconds(value):
    if isinstance(value, bool):
        raise ValueError('Timing must be a finite nonnegative number')
    try:
        result = float(value)
    except (ValueError, TypeError) as exc:
        raise ValueError('Timing must be a finite nonnegative number') from exc
    if not math.isfinite(result) or result < 0:
        raise ValueError('Timing must be a finite nonnegative number')
    return result


class RoundEvidence:
    def __init__(self, session_id, source_sha256, rules, game_deadline, *, ready_at=None):
        if len(rules) != 3 or not any(rule.get('enabled') for rule in rules):
            raise ValueError('Evidence requires three rules and an enabled region')
        self.session_id, self.source_sha256 = str(session_id), source_sha256
        self.rules = deepcopy(rules)
        self.game_deadline = _seconds(game_deadline)
        self.ready_at = _seconds(time.monotonic() if ready_at is None else ready_at)
        self.durations = {name: [] for name in DEFAULT_SECONDS}
        self.observations = []
        self.best = None
        self.first_usable = None
        self.return_success = None

    def record_duration(self, stage, seconds):
        if stage not in self.durations:
            raise ValueError('Unknown stage: ' + str(stage))
        self.durations[stage].append(_seconds(seconds))

    def mark_return(self, success):
        if success is not None and not isinstance(success,bool):
            raise ValueError('Return result must be observed true/false or unknown')
        self.return_success=success

    @contextmanager
    def measure(self, stage, *, clock=time.perf_counter):
        start = clock()
        try:
            yield
        finally:
            self.record_duration(stage, clock() - start)

    def estimate_seconds(self, stage, *, floor=None):
        if stage not in self.durations:
            raise ValueError('Unknown stage: ' + str(stage))
        samples = self.durations[stage]
        base = max(DEFAULT_SECONDS[stage], 0. if floor is None else _seconds(floor))
        if not samples:
            return base
        estimate = max(samples) if len(samples) < 20 else float(np.percentile(samples, 95))
        return max(base, estimate)

    def record_observation(self, codes, frame_ids, pose, pose_epoch, verified, now,
                           *, positioned=False):
        if len(codes) != 3:
            raise ValueError('Observation requires three HEX entries')
        now = _seconds(now)
        if pose is not None:
            matrix = np.asarray(pose, float)
            if matrix.shape not in ((2, 3), (3, 3)) or not np.isfinite(matrix).all():
                raise ValueError('Observation pose must be a finite affine matrix')
            pose = matrix.tolist()
        actual, deltas = [], []
        for code, rule in zip(codes, self.rules):
            value = normalize_hex(code) if code is not None and rule.get('enabled') else None
            actual.append(value)
            deltas.append(error(value, rule['colors'], False) if value is not None else None)
        enabled = [i for i, rule in enumerate(self.rules) if rule.get('enabled')]
        complete = all(actual[i] is not None for i in enabled)
        frames = tuple(frame_ids or ())
        # Caller supplies the stable-read verdict. Repeated use of one image
        # ID cannot masquerade as two independently captured frames.
        confirmed = bool(verified and complete and len(set(frames)) >= 2
                         and all(isinstance(name, str) and name for name in frames))
        ok = bool(confirmed and accepted(actual, self.rules))
        values = [deltas[i] for i in enabled] if complete else []
        exact_matches = sum(actual[i] in self.rules[i]['colors']
                            for i in enabled if self.rules[i].get('exact') and actual[i] is not None)
        maximum = max(values) if values else None
        average = sum(values)/len(values) if values else None
        row = dict(session_id=self.session_id, source_sha256=self.source_sha256,
                   frame_ids=list(frames), codes=actual, deltas=deltas,
                   maximum=maximum, average=average, exact_matches=exact_matches,
                   pose=pose, pose_epoch=pose_epoch, verified=confirmed, accepted=ok,
                   compromise=bool(confirmed and not ok), observed_at=now,
                   positioned=bool(positioned and confirmed and pose is not None))
        self.observations.append(row)
        if confirmed:
            rank = (not ok, maximum, average, -exact_matches)
            if self.best is None or rank < self.best[0]:
                self.best = rank, deepcopy(row)
        if row['positioned'] and self.first_usable is None:
            self.first_usable = max(0., now-self.ready_at)
        return deepcopy(row)

    def report(self, now):
        now = _seconds(now)
        summaries = {}
        for stage, samples in self.durations.items():
            samples=samples.copy()  # A timed-out worker may finish recording its pair.
            summaries[stage] = dict(count=len(samples), total_seconds=sum(samples),
                mean_seconds=sum(samples)/len(samples) if samples else None,
                p95_seconds=float(np.percentile(samples, 95)) if samples else None,
                estimate_seconds=self.estimate_seconds(stage),
                estimate_source=('default_floor' if not samples else
                    'observed_max_with_default_floor' if len(samples)<20 else
                    'p95_with_default_floor'))
            summaries[stage]['aggregation']='envelope' if stage=='verification' else 'stage_component'
        return dict(schema=1, session_id=self.session_id, source_sha256=self.source_sha256,
                    ready_at=self.ready_at, game_deadline=self.game_deadline,
                    elapsed_seconds=max(0., now-self.ready_at), durations=summaries,
                    first_usable_elapsed_seconds=self.first_usable,
                    return_success=self.return_success,
                    final_remaining_seconds=max(0., self.game_deadline-now),
                    remaining_source='monotonic_game_deadline',
                    observation_count=len(self.observations),
                    duration_note='Verification is a capture/OCR/registration envelope, not an additive component.',
                    current_observation=deepcopy(self.observations[-1]) if self.observations else None,
                    best_observed=deepcopy(self.best[1]) if self.best else None)
