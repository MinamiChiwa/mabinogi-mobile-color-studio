"""Observe earlier scan frames without replacing the established late sample.

The two probe captures fit inside the existing post-drag settling interval.
They never enter the atlas or trigger input. Saved comparisons provide the
missing evidence for a later, separately validated adaptive-wait policy.
"""
from dataclasses import dataclass
import time

import numpy as np
from atlas_masks import material_masks


BASELINE_SETTLE_SECONDS = .22 + .16
FIRST_PROBE_SECONDS = .08
MIN_PROBE_GAP_SECONDS = .06
SECOND_PROBE_SECONDS = .16


@dataclass
class ScanSample:
    image: np.ndarray
    capture_started: float
    captured_at: float
    timing: dict
    probes: tuple


class ScanSettlingObserver:
    """Bounded, per-session measurement; no learned setting crosses sessions."""
    def __init__(self, scene):
        self.board = tuple(map(int, scene.board))
        self.masks = material_masks(scene)
        self.disabled_reason = None
        self.rows = []

    def crop(self, image):
        l, t, r, b = self.board
        return image[t:b, l:r]

    def compare(self, a, b):
        """Inspect every training-material pixel, without resizing or tolerance."""
        if (a.shape != b.shape or a.shape != (*self.masks.shape[1:], 3)
                or a.dtype != np.uint8 or b.dtype != np.uint8
                or not all(mask.any() for mask in self.masks)):
            return dict(equal=False, reason='invalid_geometry', regions=[])
        changed = ((a[:,:,0] != b[:,:,0]) | (a[:,:,1] != b[:,:,1])
                   | (a[:,:,2] != b[:,:,2]))
        regions = [dict(region=i+1, pixels=int(mask.sum()),
                        changed_pixels=int(np.count_nonzero(changed & mask)))
                   for i, mask in enumerate(self.masks)]
        return dict(equal=not any(row['changed_pixels'] for row in regions),
                    reason='compared', regions=regions)

    def capture_step(self, game, scene, action, previous, clock=None):
        clock = clock or time.monotonic
        started = clock()
        game.check()
        # Preserve the exact drag descriptor and all button-down/up timing.
        game.drag(scene.board, action['dx'], action['dy'])
        released_at = clock()
        # Input is already released. Cursor parking and board settling can
        # overlap; the production screenshot still waits the full .38 s.
        game.move_to((int(game.initial[2]*.5), int(game.initial[3]*.15)))
        parked_at = clock()
        deadline = parked_at + BASELINE_SETTLE_SECONDS
        probes = []
        probe_times = []
        reason = self.disabled_reason

        def wait_until(target):
            remaining = target-clock()
            if remaining > 0:
                precise_wait=getattr(game,'pause_until',None)
                if callable(precise_wait):precise_wait(target)
                else:game.pause(remaining)
            game.check()

        def observe(label, target):
            wait_until(target)
            before = clock()
            image = game.capture()
            after = clock()
            game.check()
            probes.append((label, self.crop(image).copy()))
            probe_times.append(dict(name=label, start_seconds=before-parked_at,
                                    end_seconds=after-parked_at,
                                    capture_seconds=after-before))
            return after

        if reason is None:
            try:
                first_done = observe('early', parked_at+FIRST_PROBE_SECONDS)
                second_at = max(parked_at+SECOND_PROBE_SECONDS,
                                first_done+MIN_PROBE_GAP_SECONDS)
                # Slow capture devices keep the original scan. Do not keep
                # adding probes when they consume the whole waiting interval.
                if second_at + (probe_times[0]['capture_seconds']) + .025 < deadline:
                    observe('check', second_at)
                else:
                    reason = self.disabled_reason = 'probe_capture_too_slow'
            except (OSError, ValueError, RuntimeError) as exc:
                # Optional observation failure is not a scan failure. The
                # normal guard and baseline capture below must still succeed.
                reason = self.disabled_reason = 'probe_unavailable: '+str(exc)

        wait_until(deadline)
        capture_started = clock()
        image = game.capture()
        captured_at = clock()
        game.check()
        if capture_started > deadline + .025 and reason is None:
            reason = self.disabled_reason = 'probe_budget_overrun'
        comparison_started = clock()
        comparisons = {}
        try:
            if len(probes) == 2:
                comparisons = dict(
                    early_to_check=self.compare(probes[0][1], probes[1][1]),
                    check_to_reference=self.compare(probes[1][1], self.crop(image)),
                    previous_to_reference=self.compare(self.crop(previous), self.crop(image)))
        except (ValueError, TypeError) as exc:
            reason = self.disabled_reason = 'comparison_unavailable: '+str(exc)
        comparison_seconds = clock()-comparison_started
        valid = bool(comparisons and all(row['reason']=='compared' for row in comparisons.values()))
        if comparisons and not valid:
            reason = self.disabled_reason = 'invalid_comparison_geometry'
        matched = bool(valid and comparisons['early_to_check']['equal']
                       and comparisons['check_to_reference']['equal'])
        changed = bool(valid and not comparisons['previous_to_reference']['equal'])
        # Estimate only the removed wait and final capture. Keep both early
        # captures and the measured comparison cost in a prospective policy.
        saving = (max(0., captured_at-parked_at-probe_times[-1]['end_seconds']
                      -comparison_seconds) if matched and changed else 0.)
        row = dict(mode='observe_only', selected='baseline',
                   dx=action['dx'], dy=action['dy'],
                   drag_seconds=released_at-started, park_seconds=parked_at-released_at,
                   settle_target_seconds=BASELINE_SETTLE_SECONDS,
                   baseline_start_seconds=capture_started-parked_at,
                   baseline_capture_seconds=captured_at-capture_started,
                   baseline_late_seconds=max(0.,capture_started-deadline),
                   probe_times=probe_times, comparisons=comparisons,
                   comparison_seconds=comparison_seconds,
                   early_matches_baseline=matched, motion_observed=changed,
                   potential_saving_seconds=saving,
                   fallback_reason=reason, total_seconds=clock()-started)
        self.rows.append(row)
        return ScanSample(image, capture_started, captured_at, row, tuple(probes))

    def summary(self):
        return dict(mode='observe_only', frames=len(self.rows),
                    compared_frames=sum(bool(r['comparisons']) for r in self.rows),
                    identical_early_frames=sum(r['early_matches_baseline'] for r in self.rows),
                    moved_frames=sum(r['motion_observed'] for r in self.rows),
                    potential_saving_seconds=sum(r['potential_saving_seconds'] for r in self.rows),
                    baseline_late_seconds=sum(r['baseline_late_seconds'] for r in self.rows),
                    comparison_seconds=sum(r['comparison_seconds'] for r in self.rows),
                    disabled_reason=self.disabled_reason)
