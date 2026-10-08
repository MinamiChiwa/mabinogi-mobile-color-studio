"""Current-frame, bounded single-region search.

The IO object supplies capture(), drag(board, dx, dy), wheel(board, steps,
anchor=None),
read(image, *, enabled, deadline), measure(before, after, scene), check(),
clock(), pause(seconds), and emit(kind, **data). Measure returns an affine
matrix in board-local coordinates unless its optional ``origin`` says
otherwise. No window, mouse, map or rotation implementation lives here.
Screenshot colors select proposals; only consecutive game HEX reads verify a
result. Integer wheel inputs are measured; reverse notches are not an undo.
"""
from dataclasses import dataclass
import math

import cv2
import numpy as np

from atlas_masks import material_masks
from input_gestures import drag_gesture
from vision import accepted, error, lab, rgb
from workflow_budget import WorkflowBudget


@dataclass(frozen=True)
class QuickSearchLimits:
    max_translation_fraction: float = .18
    exploration_fraction: float = .14
    max_explorations: int = 6
    max_candidate_trials: int = 6
    max_moves: int = 18
    max_target_steps: int = 8
    max_return_steps: int = 8
    max_no_improvement: int = 3
    precision_search_seconds: float = 60.
    precision_finish_grace_seconds: float = 6.
    precision_max_moves: int = 96
    precision_max_candidate_trials: int = 48
    precision_max_explorations: int = 96
    max_zoom_levels: int = 16
    max_zoom_steps_per_action: int = 4
    zoom_min_relative_scale: float = .85
    zoom_max_relative_scale: float = 1.18
    max_observation_frames: int = 3
    max_capture_attempts: int = 3
    max_local_trials: int = 2
    candidate_count: int = 8
    settle_seconds: float = .20
    verification_gap_seconds: float = .12
    observation_reserve_seconds: float = 2.5
    step_reserve_seconds: float = 1.8
    # The live Windows entry point raises this to 15 seconds for a real
    # 120-second round.  Keep the library default small for deterministic
    # simulation/replay callers that provide their own deadline budget.
    finish_reserve_seconds: float = 1.
    landing_tolerance: float = .75

    def __post_init__(self):
        if not 0 < self.max_translation_fraction <= .18:
            raise ValueError('Single-region translation fraction must be in (0, .18]')
        if not 0 < self.exploration_fraction <= self.max_translation_fraction:
            raise ValueError('Exploration must fit the translation bound')
        for name in ('max_explorations', 'max_candidate_trials', 'max_moves',
                     'max_target_steps', 'max_return_steps', 'max_no_improvement',
                     'max_observation_frames', 'max_capture_attempts',
                     'max_local_trials', 'candidate_count', 'precision_max_moves',
                     'precision_max_candidate_trials', 'precision_max_explorations',
                     'max_zoom_levels', 'max_zoom_steps_per_action'):
            value = getattr(self, name)
            minimum = 0 if name in ('max_explorations', 'max_local_trials', 'max_zoom_levels') else 1
            if isinstance(value, bool) or int(value) != value or value < minimum:
                raise ValueError('Invalid single-region limit: ' + name)
        for name in ('precision_search_seconds', 'precision_finish_grace_seconds',
                     'zoom_min_relative_scale',
                     'zoom_max_relative_scale', 'settle_seconds', 'verification_gap_seconds',
                     'observation_reserve_seconds', 'step_reserve_seconds',
                     'finish_reserve_seconds', 'landing_tolerance'):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0:
                raise ValueError('Invalid single-region timing: ' + name)
        if not (.5 <= self.zoom_min_relative_scale < 1 <= self.zoom_max_relative_scale):
            raise ValueError('Invalid single-region zoom scale bounds')
        if self.max_zoom_steps_per_action > 4:
            raise ValueError('A wheel action may use at most four notches')


def _rendered_target(values):
    """The alternate quantized linear-light swatch already used by HEX OCR."""
    srgb = np.asarray(values, dtype=float) / 255
    linear = np.where(srgb <= .04045, srgb / 12.92,
                      ((srgb + .055) / 1.055) ** 2.4)
    linear = np.rint(linear * 255) / 255
    return np.rint(255 * np.where(linear <= .0031308, linear * 12.92,
                                 1.055 * linear ** (1 / 2.4) - .055)).astype(np.uint8)


def visible_candidates(image, scene, rules, *, limit=8, excluded=(), material_mask=None):
    """Search every native pixel of the enabled material, excluding all UI.

    A 3 x 3 worst-pixel risk is retained separately from center error. Native
    exact-color seeds form a separate branch, so a one-pixel dark island is
    not lost by smoothing or downsampling. The linear-light variant is a
    plausible screenshot rendering, never evidence of actual game HEX.
    """
    enabled = [i for i, rule in enumerate(rules) if rule.get('enabled')]
    if len(rules) != 3 or len(enabled) != 1:
        raise ValueError('Single-region search requires exactly one enabled region')
    region = enabled[0]
    l, t, r, b = map(int, scene.board)
    if (image.ndim != 3 or image.shape[2] < 3 or l < 0 or t < 0 or
            r > image.shape[1] or b > image.shape[0]):
        raise ValueError('Invalid current-frame search geometry')
    pixels = image[t:b, l:r, :3]
    # Geometry is constant throughout a single-region run.  Callers may pass
    # the precomputed region mask to avoid rebuilding three full-board masks
    # for every screenshot; excluded points remain per-call and are applied
    # below.
    valid = ((material_masks(scene)[region] if material_mask is None else
              np.asarray(material_mask, dtype=bool))).copy()
    # Neighborhood risk needs supported pixels, not UI or cross-material data.
    supported = cv2.erode(valid.astype(np.uint8), np.ones((3, 3), np.uint8),
                          borderType=cv2.BORDER_CONSTANT, borderValue=0).astype(bool)
    yy, xx = np.mgrid[:b-t, :r-l]
    for x, y in excluded:
        supported &= (xx + l - x) ** 2 + (yy + t - y) ** 2 > 16
    ids = np.flatnonzero(supported.ravel())
    if not len(ids):
        return []
    rule = rules[region]
    native_targets = np.asarray([rgb(color) for color in rule['colors']], np.uint8)
    targets = np.unique(np.concatenate((native_targets, _rendered_target(native_targets))), axis=0)
    pixel_lab = lab(pixels.reshape(-1, 3)).reshape(*pixels.shape[:2], 3)
    distance = np.full(pixels.shape[:2], np.inf, dtype=np.float32)
    exact_center = np.zeros(pixels.shape[:2], dtype=bool)
    for target, target_lab in zip(targets, lab(targets)):
        distance = np.minimum(distance, np.linalg.norm(pixel_lab - target_lab, axis=2))
        exact_center |= np.all(pixels == target, axis=2)
    worst = cv2.dilate(distance, np.ones((3, 3), np.uint8))
    exact_neighborhood = cv2.erode(exact_center.astype(np.uint8), np.ones((3, 3), np.uint8),
                                  borderType=cv2.BORDER_CONSTANT, borderValue=0).astype(bool)
    center = distance.ravel()[ids]
    risk = worst.ravel()[ids]
    marker = np.asarray(scene.markers[region], float)
    sources = np.column_stack((xx.ravel()[ids] + l, yy.ravel()[ids] + t))
    moves = np.sum((sources - marker) ** 2, axis=1)
    is_exact = bool(rule.get('exact'))
    predicted = (exact_neighborhood.ravel()[ids] if is_exact else
                 (center <= float(rule['tolerance'])) & (risk <= float(rule['tolerance'])))
    # Exact mode keeps the native exact branch even when it is a tiny island;
    # stability and center error still decide between seeds in that branch.
    branch = ~exact_center.ravel()[ids] if is_exact else ~predicted
    robust_order = np.lexsort((moves, center, risk, ~predicted, branch))
    center_order = np.lexsort((moves, risk, center, ~predicted, branch))
    # Keep both stable interiors and the best native center seeds. In the
    # single-region game a very small dark spot can be useful after a bounded
    # HEX correction; a worst-neighbor-only list would hide it completely.
    order = np.column_stack((robust_order, center_order)).ravel()
    rows = []
    for index in order:
        source = sources[index]
        if any(np.sum((source - row['source']) ** 2) <= 16 for row in rows):
            continue
        rows.append(dict(region=region, source=source.astype(float),
                         center_delta=float(center[index]), worst_delta=float(risk[index]),
                         predicted_accepted=bool(predicted[index]),
                         screenshot_exact=bool(exact_center.ravel()[ids[index]]),
                         color='#%02X%02X%02X' % tuple(pixels.reshape(-1, 3)[ids[index]])))
        if len(rows) >= limit:
            break
    return rows


# Keep test/integration planners that replace ``visible_candidates`` with the
# historical four-argument callable source-compatible while the production
# path uses the precomputed mask.
_VISIBLE_CANDIDATES_IMPL = visible_candidates


def global_motion(measurement, board):
    """Convert measured affine motion to full client-image coordinates."""
    if not isinstance(measurement, dict):
        return None
    try:
        raw = np.asarray(measurement['matrix'], float)
        matrix = np.eye(3)
        if raw.shape == (3, 3):
            matrix = raw.copy()
            origin = np.asarray(measurement.get('origin', [0, 0]), float)
        elif raw.shape == (2, 3):
            matrix[:2] = raw
            origin = np.asarray(measurement.get('origin', board[:2]), float)
        else:
            return None
        if origin.shape != (2,) or not np.isfinite(matrix).all() or not np.isfinite(origin).all():
            return None
        if not np.allclose(matrix[2], [0, 0, 1], atol=1e-9):
            return None
        matrix[:2, 2] += origin - matrix[:2, :2] @ origin
        if np.linalg.det(matrix[:2, :2]) <= 0:
            return None
        return matrix
    except (KeyError, TypeError, ValueError):
        return None


class _Search:
    def __init__(self, io, scene, rules, deadline, limits, search_started_at=None):
        self.io, self.scene, self.rules = io, scene, rules
        self.deadline, self.limits = float(deadline), limits
        self.region = next(i for i, rule in enumerate(rules) if rule.get('enabled'))
        self.exact = bool(rules[self.region].get('exact'))
        self.started = io.clock() if search_started_at is None else float(search_started_at)
        self.search_deadline = (self.started + limits.precision_search_seconds
                                if self.exact else self.deadline)
        self.zoom_capable = callable(getattr(io, 'wheel', None))
        self.move_limit = (limits.precision_max_moves if self.exact and self.zoom_capable
                           else limits.max_moves)
        self.trial_limit = (limits.precision_max_candidate_trials if self.exact and self.zoom_capable
                            else limits.max_candidate_trials)
        self.exploration_limit = (limits.precision_max_explorations if self.exact and self.zoom_capable
                                  else limits.max_explorations)
        self.enabled = [i == self.region for i in range(3)]
        self.marker = np.asarray(scene.markers[self.region], float)
        l, t, r, b = scene.board
        self.cap = np.maximum(1, np.floor(np.asarray([r-l, b-t]) * limits.max_translation_fraction)).astype(int)
        self.pose = np.eye(3)
        self.epoch = 0
        self.image = None
        self.colors = [None] * 3
        self.verified = False
        self.current = False
        self.best = None
        self.layer_best = None
        self.restore_target = 'global_best'
        self.restore_fallback_used = False
        self.restore_fallback_verified = False
        self.moves = self.explorations = self.trials = self.no_improvement = self.local_trials = 0
        self.excluded = []
        self.step_seconds = limits.step_reserve_seconds
        self.observation_seconds = limits.observation_reserve_seconds
        self.reason = 'search_complete'
        self.restored = False
        self.zoom_actions = self.zoom_notches = 0
        self.zoom_responses = {-1: None, 1: None}
        self.zoom_blocked = set()
        self.zoom_native_limits = set()
        self.zoom_disabled = False
        self.relative_scale = 1.
        self.layer_trials = self.layer_explorations = 0
        self.zoom_target = None
        self.zoom_goal_index = 0
        self.zoom_band = [limits.zoom_min_relative_scale, limits.zoom_max_relative_scale]
        self.zoom_expansions = 0
        self.zoom_success_layers = set()
        self.zoom_unimproved_layers = set()
        self.last_zoom_improved = False
        self.last_zoom_direction = -1
        self.zoom_expansion_goals = None
        self.layer_origin = self.pose.copy()
        # The board geometry does not change during this workflow.  Reusing
        # this one material mask avoids repeated morphology/mesh allocations
        # while preserving the exact candidate exclusions.
        self.material_mask = material_masks(scene)[self.region].copy()

    def emit(self, kind, **data):
        emit = getattr(self.io, 'emit', None)
        if callable(emit):
            emit(kind, **data)

    def remaining(self):
        return self.deadline - self.io.clock()

    def search_remaining(self):
        return min(self.deadline, self.search_deadline) - self.io.clock()

    def finish_remaining(self):
        deadline = (min(self.deadline, self.search_deadline+self.limits.precision_finish_grace_seconds)
                    if self.exact else self.deadline)
        return deadline-self.io.clock()

    def zoom_layer_key(self):
        value = math.log(max(self.relative_scale,1e-9))
        nearby = [key for key in self.zoom_success_layers if abs(key-value)<.002]
        return min(nearby,key=lambda key:abs(key-value)) if nearby else round(value,4)

    def read(self, image):
        self.io.check()
        try:
            values = self.io.read(image, enabled=self.enabled,
                                  deadline=self.deadline - self.limits.finish_reserve_seconds)
            if len(values) != 3:
                return [None] * 3
            values = list(values)
            for index, value in enumerate(values):
                if not self.enabled[index] or value is None:
                    values[index] = None
                    continue
                try:
                    values[index] = '#%02X%02X%02X' % rgb(value)
                except (TypeError, ValueError, AttributeError):
                    values[index] = None
            return values
        except (OSError, ValueError, RuntimeError, TypeError, AttributeError):
            # F9/window/hard-time guards are rechecked before treating this
            # as an ordinary OCR observation miss.
            self.io.check()
            return [None] * 3

    def capture(self):
        failure = None
        for attempt in range(self.limits.max_capture_attempts):
            self.io.check()
            try:
                image = self.io.capture()
                if not isinstance(image, np.ndarray) or image.ndim != 3 or image.shape[2] < 3:
                    raise ValueError('Capture did not return an RGB frame')
            except (OSError, ValueError, RuntimeError, TypeError) as exc:
                # Only the screenshot is retried; a guard failure never
                # becomes a retry or new mouse input.
                self.io.check()
                failure = exc
                self.emit('single_capture_retry', attempt=attempt+1,
                          attempts=self.limits.max_capture_attempts)
                if (attempt+1 >= self.limits.max_capture_attempts or
                        self.remaining() <= self.limits.finish_reserve_seconds + self.limits.verification_gap_seconds):
                    break
                self.io.pause(self.limits.verification_gap_seconds)
            else:
                self.io.check()
                return image
        raise RuntimeError('Current frame temporarily unavailable') from failure

    def rank(self, colors):
        color = colors[self.region]
        if color is None:
            return (2, math.inf)
        rule = self.rules[self.region]
        return (0 if accepted(colors, self.rules) else 1,
                error(color, rule['colors'], False))

    def at_best(self):
        return bool(self.best and self.current and self.verified and
                    self.colors[self.region] == self.best['colors'][self.region])

    def observe(self, image=None):
        started = self.io.clock()
        previous = None
        frame_ids=[]
        self.verified = False
        for index in range(self.limits.max_observation_frames):
            if self.remaining() <= self.limits.finish_reserve_seconds:
                break
            if image is None:
                image = self.capture()
            self.image = image
            frame_id=getattr(self.io,'frame_id',None)
            if callable(frame_id):
                name=frame_id(image)
                if name is not None:frame_ids.append(name)
            self.colors = self.read(image)
            self.current = True
            if previous is not None and self.colors[self.region] is not None and self.colors == previous:
                self.verified = True
                break
            previous = self.colors
            image = None
            if index + 1 < self.limits.max_observation_frames:
                if self.remaining() <= self.limits.finish_reserve_seconds + self.limits.verification_gap_seconds:
                    break
                self.io.pause(self.limits.verification_gap_seconds)
        self.observation_seconds = max(self.observation_seconds, self.io.clock() - started)
        evidence=getattr(self.io,'evidence',None)
        if evidence is not None:
            evidence.record_duration('verification',self.io.clock()-started)
        # The first real HEX reads reveal slow OCR before leaving the initial
        # best. Every later move can require the same observation cost, not
        # merely one final read at the end of the whole route.
        movement = drag_gesture(self.scene.board, *self.cap).duration
        self.step_seconds = max(self.step_seconds, movement + self.limits.settle_seconds
                                + self.observation_seconds)
        improved = False
        if self.verified and (self.best is None or self.rank(self.colors) < self.best['rank']):
            self.best = dict(colors=self.colors.copy(), rank=self.rank(self.colors),
                             pose=None if self.pose is None else self.pose.copy(),
                             epoch=self.epoch, image=self.image.copy())
            improved = True
            self.zoom_unimproved_layers.discard(self.zoom_layer_key())
            self.emit('single_best', actual_colors=self.colors.copy(), delta=self.best['rank'][1])
        if self.verified and (self.layer_best is None or self.rank(self.colors) < self.layer_best['rank']):
            self.layer_best = dict(colors=self.colors.copy(), rank=self.rank(self.colors),
                                   pose=None if self.pose is None else self.pose.copy(), epoch=self.epoch)
        # The same verified HEX at the current pose is a better anchor than
        # an unnecessarily distant historical occurrence of that colour.
        if self.verified and self.pose is not None:
            if self.matches_record(self.best):
                self.best.update(pose=self.pose.copy(), epoch=self.epoch, image=self.image.copy())
            if self.matches_record(self.layer_best):
                self.layer_best.update(pose=self.pose.copy(), epoch=self.epoch)
        self.emit('single_observation', actual_colors=self.colors.copy(), verified=self.verified,
                  current=self.current, accepted=self.verified and accepted(self.colors, self.rules),
                  frame_ids=frame_ids[-2:],pose=None if self.pose is None else self.pose.tolist(),
                  pose_epoch=self.epoch)
        return improved

    def steps(self, displacement):
        return int(np.ceil(np.max(np.abs(displacement) / self.cap)))

    def return_displacement(self, prospective=None, *, target=None):
        target = self.best if target is None else target
        if target is None or target['pose'] is None or target['epoch'] != self.epoch:
            return None
        pose = self.pose if prospective is None else prospective
        if pose is None:
            return None
        # Only one pick point matters.  Locate its saved texture coordinate
        # in the CURRENT measured pose, then translate it back to the marker.
        # Restoring the old scale would need a non-invertible wheel replay and
        # is unnecessary here.  Different interpolation may still change the
        # HEX, so this geometric return always needs independent verification.
        source = pose @ np.linalg.inv(target['pose']) @ np.r_[self.marker, 1.]
        return self.marker - source[:2]

    def can_leave(self, displacement):
        outbound = self.steps(displacement)
        estimated_pose = None if self.pose is None else self.pose.copy()
        if estimated_pose is not None:
            estimated_pose[:2, 2] += displacement
        returned = self.return_displacement(estimated_pose)
        back = self.steps(returned) if returned is not None else outbound
        # A measured wheel/affine response can move the marker by one extra
        # integer drag step compared with the translation-only projection.
        # Reserve that step before leaving a verified best sample.
        if self.zoom_actions and returned is not None:
            back += 1
        # step_seconds already includes the action's measured verification
        # cost.  Do not charge the same OCR again and require every return to
        # finish before the soft search boundary. Once a verified best exists,
        # keep one additional action-sized reserve for a failed registration
        # retry. Without it, the final exploratory input can consume the only
        # time in which the saved best could still be restored.
        failure_reserve = 0.
        action_needed = (outbound*self.step_seconds + failure_reserve +
                         self.limits.finish_reserve_seconds)
        needed = ((outbound+back)*self.step_seconds + failure_reserve +
                  self.limits.finish_reserve_seconds)
        self.emit('single_budget', outbound_steps=outbound, return_steps=back,
                  needed_seconds=needed, action_needed_seconds=action_needed,
                  failure_reserve_seconds=failure_reserve,
                  remaining_seconds=self.remaining(), search_remaining_seconds=self.search_remaining(),
                  finish_remaining_seconds=self.finish_remaining())
        tail_allowed=True
        if getattr(self.io,'evidence',None) is not None:
            tail_allowed=WorkflowBudget(self.started,self.deadline,self.limits.finish_reserve_seconds).allow_operation(
                now=self.io.clock(),operation_seconds=outbound*self.step_seconds,
                return_seconds=back*self.step_seconds,verification_seconds=self.observation_seconds)
        return (tail_allowed and back <= self.limits.max_return_steps and self.search_remaining() >= action_needed and
                self.finish_remaining() >= needed)

    def move(self, displacement, *, restoring=False):
        ratio = max(1., float(np.max(np.abs(displacement) / self.cap)))
        command = np.rint(displacement / ratio).astype(int)
        command = np.clip(command, -self.cap, self.cap)
        if not command.any():
            return np.eye(3)
        if not restoring and self.moves >= self.move_limit:
            return None
        available = self.finish_remaining() if restoring else self.remaining()
        if available <= self.step_seconds + self.limits.finish_reserve_seconds:
            self.reason = 'return_budget'
            return None
        self.io.check()
        before = self.image
        started = self.io.clock()
        self.current = self.verified = False
        self.colors = [None] * 3
        try:
            prior_input_stage=getattr(self.io,'input_stage','input')
            self.io.input_stage='return' if restoring else 'input'
            try:self.io.drag(self.scene.board, int(command[0]), int(command[1]))
            finally:self.io.input_stage=prior_input_stage
            self.moves += 1
            self.io.pause(self.limits.settle_seconds)
            after = self.capture()
        except (OSError, ValueError, RuntimeError):
            self.io.check()
            self.pose = None
            self.excluded.clear()
            self.reason = 'input_unverified'
            try:
                self.observe()
            except (OSError, ValueError, RuntimeError):
                self.io.check()
            return None
        try:
            measured = self.io.measure(before, after, self.scene)
            matrix = global_motion(measured, self.scene.board)
        except (OSError, ValueError, RuntimeError):
            self.io.check()
            matrix = None
        if matrix is not None:
            extent = max(self.scene.board[2]-self.scene.board[0], self.scene.board[3]-self.scene.board[1])
            # An intentional wheel response is handled separately.  A drag
            # unexpectedly rotating/scaling cannot silently become a valid
            # historical return pose.
            if np.linalg.norm(matrix[:2, :2]-np.eye(2), ord=2)*extent > self.limits.landing_tolerance:
                matrix = None
                self.zoom_disabled = True
        if matrix is None:
            self.pose = None
            self.excluded.clear()
            self.zoom_disabled = True
            # A live single-region session can no longer map a screen point
            # back to a saved sample after registration fails.  Do not let
            # the next loop create a fresh epoch and continue moving: that
            # would strand ``best`` and leave the player at an arbitrary,
            # potentially worse colour.  Fake/read-only IO used by tests has
            # no wheel input and may still inspect a fresh frame; real live
            # IO exposes wheel(), so halt all further input there.
            if self.zoom_capable:
                self.reason = 'input_unverified'
        elif self.pose is not None:
            self.pose = matrix @ self.pose
            self.excluded = [(matrix @ np.r_[point, 1])[:2] for point in self.excluded]
        self.image = after
        improved = self.observe(after)
        self.no_improvement = 0 if improved else self.no_improvement + 1
        self.step_seconds = max(self.step_seconds, self.io.clock() - started,
                                drag_gesture(self.scene.board, *command).duration)
        self.emit('single_action', dx=int(command[0]), dy=int(command[1]), restoring=restoring,
                  measured=matrix is not None, matrix=None if matrix is None else matrix.tolist(),
                  pose=None if self.pose is None else self.pose.tolist(), actual_colors=self.colors.copy())
        return matrix

    def next_zoom(self, *, native_seed=False):
        """Choose measured integer detents across a bounded range of scales.

        A direction has no usable step size before its first measured notch.
        Goals are exploration levels, never a claim about the game's absolute
        zoom or an inverse command to restore a saved result.
        """
        if (not self.zoom_capable or self.zoom_disabled or self.pose is None or
                self.zoom_actions >= self.limits.max_zoom_levels or
                self.moves >= self.move_limit):
            return None
        if (self.exact and self.zoom_expansions == 0 and
                any(self.zoom_responses[d] is not None for d in (-1,1)) and
                all(self.zoom_responses[d] is not None or d in self.zoom_native_limits for d in (-1,1)) and
                len(self.zoom_unimproved_layers) >= 3):
            self.zoom_band = [min(self.zoom_band[0],.75), max(self.zoom_band[1],1.33)]
            self.zoom_expansions = 1
            self.zoom_goal_index = 0
            self.zoom_target = None
            lo,hi = self.zoom_band
            self.zoom_expansion_goals = ((1.25,hi,.80,lo) if self.last_zoom_direction>0
                                         else (.80,lo,1.25,hi))
            self.emit('single_zoom_band', local_zoom_band=self.zoom_band.copy(),
                      zoom_expansions=self.zoom_expansions,
                      reason='three_unimproved_measured_layers')
        low, high = self.zoom_band
        scale = self.relative_scale
        if self.zoom_expansions == 0:
            goals = (.96, 1.04, .90, 1.10, low, high, 1.)
        else:
            goals = self.zoom_expansion_goals
        if native_seed and self.zoom_target is None and scale < high-.003:
            # Enlarge a promising native exact island locally instead of
            # continuing a wide-view sweep at its worst sampling resolution.
            self.zoom_target = min(high, scale*1.04)
        for _ in range(len(goals)+1):
            if self.zoom_target is None:
                if self.zoom_goal_index >= len(goals):
                    return None
                self.zoom_target = goals[self.zoom_goal_index]
                self.zoom_goal_index += 1
            target = self.zoom_target
            direction = 1 if target > scale else -1
            tick = self.zoom_responses[direction]
            tolerance = max(.002, .6*abs(tick or 0.))
            if abs(math.log(target/scale)) <= tolerance or direction in self.zoom_blocked:
                self.zoom_target = None
                continue
            # A real limit hit is never followed by more notches in the same
            # direction.  An overshoot of our local band is also corrected
            # toward the band, not used for further extreme-scale searching.
            if scale < low:
                direction, target = 1, low
            elif scale > high:
                direction, target = -1, high
            tick = self.zoom_responses[direction]
            if direction in self.zoom_blocked:
                self.zoom_target = None
                continue
            if tick is None:
                return direction
            count = max(1, min(self.limits.max_zoom_steps_per_action,
                               int(round(abs(math.log(target/scale))/abs(tick)))))
            boundary = high if direction > 0 else low
            available = max(0, int(math.floor(abs(math.log(boundary/scale))/abs(tick)+1e-7)))
            if low <= scale <= high and available == 0:
                self.zoom_target = None
                continue
            if low <= scale <= high:
                count = min(count, available)
            else:
                count = 1
            return direction*count
        return None

    def can_zoom(self, steps):
        if self.pose is None:
            return False
        direction = 1 if steps > 0 else -1
        tick = self.zoom_responses[direction]
        factors = ([math.exp(steps*abs(tick))] if tick is not None else
                   [self.zoom_band[0]/self.relative_scale,
                    self.zoom_band[1]/self.relative_scale])
        back_steps = 1
        for factor in factors:
            projected = np.eye(3)
            projected[:2, :2] *= factor
            projected[:2, 2] = self.marker*(1-factor)
            delta = self.return_displacement(projected@self.pose)
            if delta is not None:
                back_steps = max(back_steps, self.steps(delta))
        # The post-action registration path has its own safety stop. Keep the
        # ordinary route budget unchanged so a failed fit does not shorten
        # the bounded search solely because of this bookkeeping.
        failure_reserve = 0.
        action_needed = (self.step_seconds + failure_reserve +
                         self.limits.finish_reserve_seconds)
        needed = ((1+back_steps)*self.step_seconds + failure_reserve +
                  self.limits.finish_reserve_seconds)
        self.emit('single_budget', action='wheel', wheel_steps=int(steps),
                  return_steps=back_steps, needed_seconds=needed,
                  action_needed_seconds=action_needed, remaining_seconds=self.remaining(),
                  search_remaining_seconds=self.search_remaining(),
                  finish_remaining_seconds=self.finish_remaining(),
                  failure_reserve_seconds=failure_reserve)
        tail_allowed=True
        if getattr(self.io,'evidence',None) is not None:
            tail_allowed=WorkflowBudget(self.started,self.deadline,self.limits.finish_reserve_seconds).allow_operation(
                now=self.io.clock(),operation_seconds=self.step_seconds,
                return_seconds=back_steps*self.step_seconds,verification_seconds=self.observation_seconds)
        return (tail_allowed and back_steps <= self.limits.max_return_steps and self.search_remaining() >= action_needed and
                self.finish_remaining() >= needed)

    def zoom(self, steps):
        """Measure a wheel action before trusting either its pose or response."""
        if not self.can_zoom(steps):
            self.reason = 'return_budget'
            return False
        self.io.check()
        before = self.image
        started = self.io.clock()
        self.current = self.verified = False
        self.colors = [None]*3
        try:
            self.io.wheel(self.scene.board, int(steps), anchor=tuple(self.marker))
            self.moves += 1
            self.zoom_actions += 1
            self.zoom_notches += abs(int(steps))
            self.io.pause(self.limits.settle_seconds)
            after = self.capture()
        except (OSError, ValueError, RuntimeError):
            self.io.check()
            self.pose = None
            self.zoom_disabled = True
            self.excluded.clear()
            self.reason = 'input_unverified'
            try: self.observe()
            except (OSError, ValueError, RuntimeError): self.io.check()
            return False
        matrix = None
        try:
            matrix = global_motion(self.io.measure(before, after, self.scene), self.scene.board)
            if matrix is None and self.search_remaining() > self.observation_seconds:
                # A settling or feature failure gets one read-only fresh
                # frame.  No blind reverse notch is emitted on a failed fit.
                self.io.pause(self.limits.verification_gap_seconds)
                after = self.capture()
                matrix = global_motion(self.io.measure(before, after, self.scene), self.scene.board)
        except (OSError, ValueError, RuntimeError):
            self.io.check()
            matrix = None
        direction = 1 if steps > 0 else -1
        scale = None
        if matrix is not None:
            linear = matrix[:2, :2]
            scale = float(math.hypot(linear[0, 0], linear[1, 0]))
            angle = float(math.degrees(math.atan2(linear[1, 0], linear[0, 0])))
            if (scale <= 0 or abs(angle) > .5 or
                    not np.allclose(linear, [[linear[0, 0], -linear[1, 0]],
                                             [linear[1, 0], linear[0, 0]]], atol=1e-6)):
                matrix = None
            else:
                observed = math.log(scale)
                if abs(observed) < .001:
                    self.zoom_blocked.add(direction)
                    self.zoom_native_limits.add(direction)
                    self.zoom_target = None
                elif observed*direction <= 0:
                    # A wrong-direction response may still be geometrically
                    # measured, but it cannot calibrate further inputs.
                    self.zoom_blocked.add(direction)
                    self.zoom_target = None
                else:
                    self.zoom_responses[direction] = abs(observed/steps)
                    self.last_zoom_direction = direction
                self.pose = matrix@self.pose
                self.relative_scale = float(math.hypot(self.pose[0, 0], self.pose[1, 0]))
        if matrix is None:
            self.pose = None
            self.zoom_disabled = True
            # The wheel did happen, but its affine response is unknown.  A
            # blind follow-up move (or a new pose epoch) cannot safely return
            # to a verified historical best, so finish on this observed
            # frame and release input.  The caller still reports the saved
            # best separately when it cannot be re-established.
            self.reason = 'input_unverified'
        self.image = after
        # A failed point at one scale can become useful after resampling.
        self.excluded.clear()
        self.no_improvement = self.layer_trials = self.layer_explorations = 0
        self.layer_best = None
        self.layer_origin = None if self.pose is None else self.pose.copy()
        prior = None if self.best is None else self.best['rank']
        improved = self.observe(after)
        self.last_zoom_improved = bool(improved or (prior is not None and self.best is not None and self.best['rank'] < prior))
        if matrix is not None and scale is not None and abs(math.log(scale))>=.001:
            key = self.zoom_layer_key()
            self.zoom_success_layers.add(key)
            if self.last_zoom_improved:
                self.zoom_unimproved_layers.discard(key)
            else:
                self.zoom_unimproved_layers.add(key)
        self.step_seconds = max(self.step_seconds, self.io.clock()-started)
        self.emit('single_zoom', wheel_steps=int(steps), anchor=self.marker.tolist(),
                  measured=matrix is not None, matrix=None if matrix is None else matrix.tolist(),
                  response_scale=scale, relative_scale=self.relative_scale,
                  directional_log_steps={str(k):v for k, v in self.zoom_responses.items()},
                  local_zoom_band=self.zoom_band.copy(), zoom_expansions=self.zoom_expansions,
                  successful_zoom_layers=len(self.zoom_success_layers),
                  unimproved_zoom_layers=len(self.zoom_unimproved_layers),
                  blocked_directions=sorted(self.zoom_blocked),
                  actual_colors=self.colors.copy(), verified=self.verified)
        return matrix is not None

    def pursue(self, source):
        source = np.asarray(source, float).copy()
        for _ in range(self.limits.max_target_steps):
            delta = self.marker - source
            if np.max(np.abs(delta)) <= self.limits.landing_tolerance:
                return 'landed', source
            if self.moves >= self.move_limit:
                return 'move_limit', source
            if not self.can_leave(delta):
                return 'return_budget', source
            matrix = self.move(delta)
            if matrix is None:
                return 'pose_unverified', None
            source = (matrix @ np.r_[source, 1])[:2]
            if self.verified and accepted(self.colors, self.rules):
                return 'matched', source
        return 'target_limit', source

    def local_probe(self, source):
        """Try at most two integer neighbors of a native exact screenshot seed.

        The marker corridor hides the landed source. Game HEX therefore
        decides whether the tiny seed was actually sampled. Neighbors are
        relative to the measured landing pose, never a blind command undo.
        """
        if self.pose is None or self.limits.max_local_trials == 0:
            return source
        base_pose = self.pose.copy()
        residual = self.marker - source
        first = np.clip(np.rint(residual), -1, 1).astype(int)
        if not first.any():
            axis = int(np.argmax(np.abs(residual)))
            first[axis] = 1 if residual[axis] >= 0 else -1
        second = np.zeros(2, dtype=int)
        axis = 1 if first[0] else 0
        second[axis] = 1 if residual[axis] >= 0 else -1
        for offset in (first, second)[:self.limits.max_local_trials]:
            if self.pose is None or self.moves >= self.move_limit:
                break
            relative = self.pose @ np.linalg.inv(base_pose)
            extent = max(self.scene.board[2]-self.scene.board[0], self.scene.board[3]-self.scene.board[1])
            if np.linalg.norm(relative[:2, :2]-np.eye(2), ord=2)*extent > self.limits.landing_tolerance:
                break
            actual = relative[:2, :2] @ self.marker + relative[:2, 2] - self.marker
            delta = np.asarray(offset, float) - actual
            if not self.can_leave(delta):
                break
            self.local_trials += 1
            self.emit('single_local_probe', trial=self.local_trials, offset=offset.tolist())
            matrix = self.move(delta)
            if matrix is None:
                return None
            source = (matrix @ np.r_[source, 1])[:2]
            if self.verified and accepted(self.colors, self.rules):
                break
        return source

    def matches_record(self, record):
        return bool(record and self.current and self.verified and
                    self.colors[self.region] == record['colors'][self.region])

    def restore_record(self, record):
        if self.matches_record(record):
            return True
        for _ in range(self.limits.max_return_steps):
            delta = self.return_displacement(target=record)
            if delta is None:
                return False
            if np.max(np.abs(delta)) <= self.limits.landing_tolerance:
                # Geometric arrival alone never confirms the saved HEX.
                if self.finish_remaining() <= self.observation_seconds+self.limits.finish_reserve_seconds:
                    return False
                self.observe()
                return self.matches_record(record)
            if (self.steps(delta) > self.limits.max_return_steps or
                    self.finish_remaining() <= self.steps(delta)*self.step_seconds+self.limits.finish_reserve_seconds):
                return False
            if self.move(delta, restoring=True) is None:
                return False
            if self.matches_record(record):
                return True
        return False

    def restore(self):
        if self.best is None or self.at_best():
            return
        # Keep a verified same-scale alternative before trying the global
        # sample.  The global sample may have been observed at another scale
        # and therefore may not reproduce its exact interpolated colour.
        alternatives = []
        if self.layer_best is not None:
            alternatives.append(self.layer_best)
        if self.current and self.verified and self.pose is not None:
            alternatives.append(dict(colors=self.colors.copy(), rank=self.rank(self.colors),
                                     pose=self.pose.copy(), epoch=self.epoch))
        alternatives = [row for row in alternatives if row['pose'] is not None and row['epoch']==self.epoch]
        fallback = min(alternatives, key=lambda row:row['rank']) if alternatives else None
        delta = self.return_displacement()
        attempt_global = delta is not None
        if attempt_global and fallback is not None:
            projected = self.pose.copy()
            projected[:2, 2] += delta
            back = self.return_displacement(projected, target=fallback)
            outbound_steps = self.steps(delta)
            fallback_steps = self.steps(back) if back is not None else self.limits.max_return_steps+1
            # Budget both legs before departing a usable result.  If the
            # second leg would not fit, retain/restore the same-scale result.
            needed = (outbound_steps+fallback_steps)*self.step_seconds+self.observation_seconds+self.limits.finish_reserve_seconds
            attempt_global = (max(outbound_steps,fallback_steps)<=self.limits.max_return_steps and
                              self.finish_remaining()>=needed)
        if attempt_global and self.restore_record(self.best):
            self.restored = self.at_best()
            return
        if fallback is not None and (not self.verified or self.rank(self.colors)>fallback['rank']):
            self.restore_target = 'same_layer_best'
            self.restore_fallback_used = True
            self.restore_fallback_verified = self.restore_record(fallback)
        self.restored = self.at_best()

    def result(self):
        # Keep the user-facing outcome explicit. A verified colour outside
        # the configured target is still a measured compromise; an
        # unverified read remains an unknown/failure state.
        accepted_result = bool(self.verified and accepted(self.colors, self.rules))
        outcome = ('matched' if accepted_result else 'compromise') if self.verified else 'unverified'
        # ``outcome`` is used by the current UI, while callers that persist
        # or relay the result should not have to infer compromise status from
        # a pair of fields.  In particular, Exact mode intentionally keeps
        # searching after a miss and returns the best *measured* colour when
        # no exact HEX was observed.  Expose that fact explicitly so a
        # near-colour can never be mistaken for an exact hit or for an
        # unexplained early stop.
        compromise = bool(self.verified and not accepted_result)
        historical_best_unrestored = bool(self.best is not None and not self.at_best())
        return dict(actual_colors=self.colors.copy(), accepted=accepted_result,
                    outcome=outcome, compromise=compromise,
                    exact_target_missed=bool(self.exact and compromise),
                    verified=self.verified, current=self.current,
                    best_actual_colors=None if self.best is None else self.best['colors'].copy(),
                    best_verified=self.best is not None, best_current=self.at_best(),
                    # This is deliberately separate from ``best_verified``:
                    # the historical sample may be valid evidence yet not be
                    # the colour currently visible in the game.
                    historical_best_unrestored=historical_best_unrestored,
                    restored=self.restored, reason=self.reason, moves=self.moves,
                    explorations=self.explorations, candidate_trials=self.trials,
                    local_trials=self.local_trials,
                    zoom_actions=self.zoom_actions, zoom_notches=self.zoom_notches,
                    relative_scale=self.relative_scale,
                    local_zoom_band=self.zoom_band.copy(), zoom_expansions=self.zoom_expansions,
                    zoom_responses={str(k):v for k, v in self.zoom_responses.items()},
                    search_elapsed_seconds=self.io.clock()-self.started,
                    restore_target=self.restore_target,
                    restore_fallback_used=self.restore_fallback_used,
                    restore_fallback_verified=self.restore_fallback_verified,
                    successful_zoom_layers=len(self.zoom_success_layers),
                    unimproved_zoom_layers=len(self.zoom_unimproved_layers),
                    pose=None if self.pose is None else self.pose.tolist())

    def run(self):
        self.emit('single_progress', stage='observe', moves=0)
        self.observe()
        if self.verified and accepted(self.colors, self.rules):
            self.reason = 'matched'
            return self.result()
        # Visit distinct quadrants around the initial view.  The old sequence
        # repeated left/down and could miss a corner while spending the same
        # input budget.
        directions = ((1, 0), (0, 1), (-1, 0), (0, -1),
                      (1, 1), (-1, 1), (-1, -1), (1, -1))
        while self.moves < self.move_limit:
            self.io.check()
            if self.search_remaining() <= self.observation_seconds + self.limits.finish_reserve_seconds:
                self.reason = ('precision_time_budget' if self.exact and
                               self.search_deadline < self.deadline else 'return_budget')
                break
            if self.reason == 'input_unverified':
                break
            if self.pose is None:
                # A fresh current-frame proposal starts a new pose epoch;
                # historical positions from the old epoch remain unreturnable.
                self.pose = np.eye(3)
                self.epoch += 1
                self.excluded.clear()
                self.layer_origin = self.pose.copy()
                self.layer_best = (dict(colors=self.colors.copy(), rank=self.rank(self.colors),
                                       pose=self.pose.copy(), epoch=self.epoch)
                                   if self.current and self.verified else None)
                if self.at_best():
                    # The best colors were independently observed at this
                    # very pose, so it can anchor the new local epoch.
                    self.best.update(pose=self.pose.copy(), epoch=self.epoch)
            self.emit('single_progress', stage='search', moves=self.moves,
                      search_elapsed_seconds=self.io.clock()-self.started,
                      relative_scale=self.relative_scale)
            if self.relative_scale < self.zoom_band[0] or self.relative_scale > self.zoom_band[1]:
                # A first unknown notch can overshoot the local band.  Do not
                # search that extreme view: only a measured, single opposite
                # notch may bring it back.  It is not a saved-result undo.
                steps = self.next_zoom()
                if steps is None:
                    self.reason = 'zoom_range_complete'
                    break
                self.zoom(steps)
                if self.verified and accepted(self.colors, self.rules):
                    self.reason = 'matched'
                    return self.result()
                if self.reason in ('input_unverified', 'return_budget'):
                    break
                continue
            candidate_kwargs = dict(limit=self.limits.candidate_count,
                                    excluded=self.excluded)
            if visible_candidates is _VISIBLE_CANDIDATES_IMPL:
                candidate_kwargs['material_mask'] = self.material_mask
            rows = visible_candidates(self.image, self.scene, self.rules,
                                      **candidate_kwargs)
            if self.verified:
                current_delta = self.rank(self.colors)[1]
                exact = bool(self.rules[self.region].get('exact'))
                # Do not spend every trial moving around a uniform, poor
                # color island. Search another overlapping view unless a
                # native exact seed or a measured-error improvement is
                # plausible. Missing score fields support injected planners.
                rows = [row for row in rows if 'center_delta' not in row or
                        row['center_delta'] < current_delta - .15 or
                        (exact and row.get('screenshot_exact')) or
                        (row.get('predicted_accepted') and not accepted(self.colors, self.rules))]
            if self.no_improvement >= self.limits.max_no_improvement:
                rows = []  # inspect another overlapping view before giving up
            if self.zoom_capable and not self.zoom_disabled and self.layer_trials >= 2:
                rows = []  # do not spend the entire search at one scale
            # A distant proposal may no longer fit while a nearby one still
            # does.  Return protection applies to that route, not to every
            # remaining action in the entire search.
            rows = [row for row in rows if self.can_leave(self.marker-np.asarray(row['source'],float))]
            if rows and self.trials < self.trial_limit:
                row = rows[0]
                self.trials += 1
                self.layer_trials += 1
                status, source = self.pursue(row['source'])
                if status == 'matched' or (self.verified and accepted(self.colors, self.rules)):
                    self.reason = 'matched'
                    return self.result()
                if (source is not None and self.rules[self.region].get('exact') and
                        row.get('screenshot_exact') and
                        np.max(np.abs(self.marker-source)) <= self.limits.landing_tolerance):
                    source = self.local_probe(source)
                    if self.verified and accepted(self.colors, self.rules):
                        self.reason = 'matched'
                        return self.result()
                if source is not None:
                    self.excluded.append(source)
                if status == 'pose_unverified' and self.reason == 'input_unverified':
                    break
                if (self.exact and row.get('screenshot_exact') and
                        self.pose is not None and source is not None):
                    steps = self.next_zoom(native_seed=True)
                    if steps is not None and self.can_zoom(steps):
                        self.emit('single_progress', stage='zoom', moves=self.moves,
                                  relative_scale=self.relative_scale)
                        self.zoom(steps)
                        if self.verified and accepted(self.colors, self.rules):
                            self.reason = 'matched'
                            return self.result()
                        if self.reason == 'input_unverified':
                            break
            else:
                steps = (self.next_zoom() if self.layer_explorations >= 1 or
                         self.layer_trials >= 2 or
                         self.no_improvement >= self.limits.max_no_improvement else None)
                if steps is not None and self.can_zoom(steps):
                    self.emit('single_progress', stage='zoom', moves=self.moves,
                              relative_scale=self.relative_scale)
                    self.zoom(steps)
                    if self.verified and accepted(self.colors, self.rules):
                        self.reason = 'matched'
                        return self.result()
                    if self.reason == 'input_unverified':
                        break
                    continue
                if self.explorations >= self.exploration_limit:
                    self.reason = 'exploration_complete'
                    break
                direction = np.asarray(directions[self.explorations % len(directions)])
                size = np.asarray([self.scene.board[2]-self.scene.board[0], self.scene.board[3]-self.scene.board[1]])
                delta = np.rint(direction * size * self.limits.exploration_fraction)
                if self.exact and self.zoom_capable and self.pose is not None and self.layer_origin is not None:
                    # At a fixed scale, visit distinct offsets around its
                    # measured starting view.  Cumulative compass commands
                    # otherwise circle back through the same few pixels.
                    relative = self.pose@np.linalg.inv(self.layer_origin)
                    current_offset = (relative@np.r_[self.marker, 1.])[:2]-self.marker
                    ring = 1 + min(2, self.layer_explorations//len(directions))
                    delta = delta*ring-current_offset
                    delta = np.clip(delta, -self.cap, self.cap)
                if not self.can_leave(delta):
                    # A shorter overlapping view can still fit after a long
                    # wheel route or distant candidate has become too costly.
                    # Do not abandon all useful work for that one proposal.
                    smaller = None
                    for fraction in (.5,.25,.125):
                        trial = np.rint(delta*fraction)
                        if trial.any() and self.can_leave(trial):
                            smaller = trial
                            break
                    if smaller is None:
                        self.reason = 'return_budget'
                        break
                    delta = smaller
                self.explorations += 1
                self.layer_explorations += 1
                # A translation exposes a new view at the same scale.  Its
                # promising seeds deserve their own short trial allowance;
                # exhausting two trials in an older view must not disable
                # target pursuit for the rest of the precision time window.
                self.layer_trials = 0
                self.no_improvement = 0
                self.move(delta)
                # A live registration failure makes the current pose
                # unknown.  Do not create a fresh pose epoch and send another
                # exploration move: that would strand a previously verified
                # best sample and can leave the player at a worse colour.
                if self.reason in ('input_unverified', 'pose_unverified'):
                    break
                # Exploration itself can land on a valid target. Do not issue
                # the next directional move before returning control to the
                # player.
                if self.verified and accepted(self.colors, self.rules):
                    self.reason = 'matched'
                    return self.result()
            if (not (self.exact and self.zoom_capable) and
                    self.no_improvement >= self.limits.max_no_improvement and
                    self.explorations >= min(2, self.limits.max_explorations)):
                self.reason = 'no_improvement'
                break
        self.emit('single_progress', stage='restore', moves=self.moves)
        self.restore()
        return self.result()


def run_single_region(io, scene, rules, *, game_deadline, search_started_at=None, limits=None):
    """Run finite local proposals/exploration and return an honest live result."""
    enabled = [i for i, rule in enumerate(rules) if rule.get('enabled')]
    if len(rules) != 3 or len(enabled) != 1:
        raise ValueError('Single-region search requires exactly one enabled region')
    if not math.isfinite(game_deadline):
        raise ValueError('Single-region search requires a finite game deadline')
    if search_started_at is not None and not math.isfinite(search_started_at):
        raise ValueError('Single-region search requires a finite start time')
    search = _Search(io, scene, rules, game_deadline, limits or QuickSearchLimits(), search_started_at)
    try:
        result = search.run()
    except (OSError, ValueError, RuntimeError):
        # Ordinary capture/OCR/planning faults stop new motion normally. A
        # user/window/game-time interruption is rechecked and propagates;
        # this layer must never trigger a return after F9.
        io.check()
        # A measured pose and a saved HEX remain usable after a non-safety
        # planning/read failure. Give the bounded return path one chance.
        if search.best is not None and search.current and search.pose is not None:
            try: search.restore()
            except (OSError, ValueError, RuntimeError): io.check()
        search.reason = 'observation_unavailable'
        result = search.result()
    search.emit('single_verified', **result)
    return result
