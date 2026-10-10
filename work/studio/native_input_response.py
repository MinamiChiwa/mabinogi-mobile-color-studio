"""Conditional offline dye-input replay. Never read a process or send input.

Screen-to-local geometry and visible samples are caller assumptions. The
float32 motion/angle kernels are backed by original-instruction fixtures.
Release velocity, inertia and UI event routing are deliberately unmodelled.
"""
from dataclasses import dataclass
import copy
import math
import numpy as np

F = np.float32


def _vector(value):
    v = np.asarray(value, dtype=np.float64)
    if v.shape != (2,) or not np.isfinite(v).all() or np.max(np.abs(v)) > np.finfo(np.float32).max:
        raise ValueError('Two finite float32 coordinates required')
    return v.astype(np.float32)


def _scalar(value):
    if not math.isfinite(value) or abs(value) > np.finfo(np.float32).max:
        raise ValueError('Finite float32 scalar required')
    return F(value)


def _pose(value):
    p = _vector(value['position'])
    scale, rotation = _scalar(value['scale']), _scalar(value['rotation_degrees'])
    if scale <= 0:
        raise ValueError('Positive native scale required')
    return dict(position=p.tolist(), scale=float(scale), rotation_degrees=float(rotation))


@dataclass(frozen=True)
class InputSettings:
    minimum_scale: float
    maximum_scale: float
    move_threshold: float
    move_tolerance: float
    scroll_zoom_ratio: float

    def __post_init__(self):
        values = [_scalar(v) for v in (self.minimum_scale, self.maximum_scale,
                   self.move_threshold, self.move_tolerance, self.scroll_zoom_ratio)]
        if not (0 < values[0] <= values[1]) or any(v < 0 for v in values[2:]):
            raise ValueError('Invalid dye input settings')


@dataclass(frozen=True)
class InputGeometry:
    """Axis-aligned physical client rect and its explicit UI local dimensions.

    local_size is not inferred from pixels. This idealized affine mapping is
    an input assumption, not a recovered RectTransform/Canvas measurement.
    windows_legacy_mouse_pixels applies the native H-y-1 cursor convention.
    An optional complete target-HWND pixel lattice explicitly maps physical
    integers through the recovered viewport floor into native board edges.
    Supplied validation metadata is a binding, not live source authentication.
    """
    board: tuple
    local_size: tuple
    input_coordinate_convention: str = 'continuous_screen_edges'
    pixel_mapping: dict | None = None

    def __post_init__(self):
        if self.input_coordinate_convention not in ('continuous_screen_edges','windows_legacy_mouse_pixels'):
            raise ValueError('Explicit supported input coordinate convention required')
        b = np.asarray(self.board, dtype=float)
        size = _vector(self.local_size)
        if b.shape != (4,) or not np.isfinite(b).all() or np.any(b[2:] <= b[:2]) or np.any(size <= 0):
            raise ValueError('Positive finite geometry required')
        object.__setattr__(self, 'board', tuple(float(v) for v in b))
        object.__setattr__(self, 'local_size', tuple(float(v) for v in size))
        if self.pixel_mapping is not None:
            if self.input_coordinate_convention != 'windows_legacy_mouse_pixels':
                raise ValueError('Pixel lattice requires the explicit legacy input convention')
            packet, pixels = _pixel_mapping(self.pixel_mapping)
            physical = packet['physical_client_size']
            if np.any(b[:2] < 0) or np.any(b[2:] > physical):
                raise ValueError('Physical board lies outside the pixel lattice')
            object.__setattr__(self, 'pixel_mapping', packet)
            object.__setattr__(self, '_native_pixels', pixels)

    def pixel_mapping_record(self):
        return copy.deepcopy(self.pixel_mapping)

    def local(self, screen):
        x, y = _vector(screen)
        if self.pixel_mapping is not None:
            # Validate before float32 conversion can hide a fractional input.
            point = np.asarray(screen, dtype=np.float64)
            size = self.pixel_mapping['physical_client_size']
            if np.any(point != np.floor(point)) or np.any(point < 0) or np.any(point >= size):
                raise ValueError('Whole physical client pixels within the measured lattice required')
            x, y = (F(axis[int(v)]) for axis, v in zip(self._native_pixels, point))
            l, t, r, b = self.pixel_mapping['native_board_top_left']
        else:
            l, t, r, b = self.board
        if self.input_coordinate_convention == 'windows_legacy_mouse_pixels':
            y = F(y+F(1))
        w, h = self.local_size
        return _vector([(float(x)-l)/(r-l)*w-w/2,
                        (b-float(y))/(b-t)*h-h/2])

    def normalized_to_physical(self, normalized):
        """Choose nearest reachable native pixel, preserving the physical route.

        This is a proposal inverse. Complete replay decides its actual endpoint.
        Ties select the first physical integer in the measured lattice.
        """
        _vector(normalized)
        u, v = np.asarray(normalized, dtype=np.float64)
        if self.pixel_mapping is None:
            l, t, r, b = self.board
            return (round(l+float(u)*(r-l)),
                    round(b-float(v)*(b-t)-(1 if self.input_coordinate_convention ==
                          'windows_legacy_mouse_pixels' else 0)))
        l, t, r, b = self.pixel_mapping['native_board_top_left']
        target = (l+float(u)*(r-l), b-float(v)*(b-t)-1)
        return tuple(int(np.argmin(np.abs(axis-value)))
                     for axis, value in zip(self._native_pixels, target))

    def native_tangent_point(self, point, *, axis=1, direction=1):
        """First physical pixel on this axis that changes the native input.

        This preserves a one-native-pixel arc when physical neighbors collapse
        on a DPI plateau. An exhausted client axis yields its outside boundary;
        existing gesture board guards then reject that proposal.
        """
        if type(axis) is not int or axis not in (0, 1) or direction not in (-1, 1):
            raise ValueError('Explicit coordinate axis and unit direction required')
        self.local(point)
        result = [int(v) for v in point]
        if self.pixel_mapping is None:
            result[axis] += direction
        else:
            pixels = self._native_pixels[axis]
            current = pixels[result[axis]]
            result[axis] = (int(np.searchsorted(pixels, current, side='right')) if direction > 0
                            else int(np.searchsorted(pixels, current, side='left'))-1)
        return tuple(result)

    def normalized(self, local):
        p = _vector(local)
        w, h = self.local_size
        # Original inverse lerp accepts float32 value and double bounds.
        return _vector([(float(p[0])-float(F(-w/2)))/float(F(w)),
                        (float(p[1])-float(F(-h/2)))/float(F(h))])


def _pixel_mapping(record):
    """Own complete measured tables; never derive Windows rounding from DPI."""
    if not isinstance(record, dict):
        raise ValueError('Explicit physical-to-native pixel mapping required')
    packet = copy.deepcopy(record)
    proof = packet.get('coordinate_validation')
    if (not isinstance(proof, dict) or proof.get('verified') is not True or
            proof.get('scheme') != 'physical_to_logical_for_hwnd_then_target_context_screen_to_client'):
        raise ValueError('Verified target-awareness coordinate validation required')
    sizes = []
    for name in ('physical_client_size', 'native_screen_size', 'target_client_size'):
        value = packet.get(name)
        if (not isinstance(value, (list, tuple)) or len(value) != 2 or
                any(type(v) is not int or not 1 <= v <= 65536 for v in value)):
            raise ValueError('Bounded whole client/screen dimensions required')
        packet[name] = list(value)
        sizes.append(value)
    board = np.asarray(packet.get('native_board_top_left'), dtype=float)
    if (board.shape != (4,) or not np.isfinite(board).all() or
            np.any(board[2:] <= board[:2]) or np.any(board[:2] < 0) or np.any(board[2:] > sizes[1])):
        raise ValueError('Native continuous board bounds required')
    packet['native_board_top_left'] = board.tolist()
    origin = np.asarray(packet.get('viewport_origin'), dtype=float)
    scale = np.asarray(packet.get('viewport_scale'), dtype=float)
    if (origin.shape != (2,) or scale.shape != (2,) or not np.isfinite(origin).all() or
            not np.isfinite(scale).all() or np.any(origin != np.floor(origin)) or np.any(scale <= 0)):
        raise ValueError('Finite native viewport origin and positive scale required')
    native_origin = [_scalar(v) for v in origin]
    packet['viewport_origin'] = [int(v) for v in origin]
    packet['viewport_scale'] = [float(_scalar(v)) for v in scale]
    pixels = []
    for axis, name in enumerate(('target_client_x_by_physical_x', 'target_client_y_by_physical_y')):
        table = packet.get(name)
        if (not isinstance(table, (list, tuple)) or len(table) != sizes[0][axis] or
                any(type(v) is not int or not 0 <= v <= sizes[2][axis] for v in table) or
                any(a > b for a, b in zip(table, table[1:]))):
            raise ValueError('Complete ordered target-client integer pixel tables required')
        packet[name] = list(table)
        # Recovered getter order: q and origin separately to float32,
        # subtract float32, multiply float32 viewport scale, floor.
        # Native Y is then H-y-1.
        native = np.floor((np.asarray(table, dtype=np.float32)-native_origin[axis])*F(scale[axis]))
        if not np.isfinite(native).all():
            raise ValueError('Native viewport pixel overflow')
        native.setflags(write=False)
        pixels.append(native)
    return packet, tuple(pixels)


def _distance(delta):
    with np.errstate(over='raise', invalid='raise'):
        try:
            d = _vector(delta)
            square = F(F(d[1]*d[1])+F(d[0]*d[0]))
            return F(math.sqrt(float(square)))
        except FloatingPointError as exc:
            raise ValueError('Distance overflow') from exc


def native_signed_angle(a, b):
    """Degree angle with original float32 dot/acos/sign arithmetic order."""
    a, b = _vector(a), _vector(b)
    with np.errstate(over='raise', invalid='raise', divide='raise'):
        try:
            a2 = F(F(a[1]*a[1])+F(a[0]*a[0]))
            b2 = F(F(b[1]*b[1])+F(b[0]*b[0]))
            denom = F(math.sqrt(float(F(a2*b2))))
            if denom < F(1e-15):
                angle = F(0)
            else:
                cosine = F(F(F(a[1]*b[1])+F(a[0]*b[0]))/denom)
                angle = F(F(math.acos(float(np.clip(cosine, F(-1), F(1)))))*F(57.29578))
            cross = F(F(b[1]*a[0])-F(b[0]*a[1]))
            return float(F(angle*(F(1) if cross >= F(0) else F(-1))))
        except FloatingPointError as exc:
            raise ValueError('Angle overflow') from exc


def virtual_rotation_delta(a, b):
    """Right-pointer angular/radial gate, vectors relative to press pivot."""
    a, b = _vector(a), _vector(b)
    r0, r1 = _distance(a), _distance(b)
    if r0 <= F(.01) or r1 <= F(.01):
        return 0.
    angle = F(native_signed_angle(a, b))
    return float(angle) if abs(F(angle/F(200))) > abs(F(r1-r0)) else 0.


def apply_motion_event(pose, pivot, move, zoom, rotation_delta, settings, *, drag_only=False):
    """One finite native motion event; no guards/callbacks/inertia simulation."""
    pose = _pose(pose)
    p, pivot, move = _vector(pose['position']), _vector(pivot), _vector(move)
    zoom, delta = _scalar(zoom), _scalar(rotation_delta)
    if drag_only and (zoom != F(1) or delta != F(0)):
        raise ValueError('Pure drag cannot zoom or rotate')
    with np.errstate(over='raise', invalid='raise', divide='raise'):
        try:
            p = p + move
            old = F(pose['scale'])
            if drag_only:
                return _pose(dict(pose, position=p))
            new = F(np.clip(F(zoom*old), F(settings.minimum_scale), F(settings.maximum_scale)))
            ratio = F(new/old)
            p = p + ((pivot-p)-F(.5))*F(F(1)-ratio)
            center = pivot-F(.5)
            d = p-center
            radians = F(delta*F(math.pi/180))
            c, s = F(math.cos(float(radians))), F(math.sin(float(radians)))
            p = [F(F(F(c*d[0])-F(s*d[1]))+center[0]),
                 F(F(F(c*d[1])+F(s*d[0]))+center[1])]
            return _pose(dict(position=p, scale=new,
                              rotation_degrees=F(F(pose['rotation_degrees'])+delta)))
        except FloatingPointError as exc:
            raise ValueError('Motion overflow') from exc


def _sampled_indices(points, policy, supplied):
    if policy == 'all_recorded_points':
        if supplied is not None:
            raise ValueError('Indices conflict with all-recorded-points policy')
        return list(range(len(points)))
    if policy != 'explicit_indices' or supplied is None:
        raise ValueError('Explicit visible sample policy required')
    indices = list(supplied)
    if (not indices or indices[0] != 0 or any(type(i) is not int for i in indices)
            or any(i < 0 or i >= len(points) for i in indices)
            or any(a >= b for a, b in zip(indices, indices[1:]))):
        raise ValueError('Sample indices must start at press and strictly increase')
    return indices


def replay_native_route(reference, route, geometry, settings, *, sample_policy,
                        sample_indices=None, wheel_delta_per_step=None,
                        check=lambda: None):
    """Replay independent gestures under an explicit, conditional sample model.

    Each pointer record begins a fresh touch. Only provided observed points
    are processed; no hidden interpolation or release-to-endpoint is invented.
    wheel_delta_per_step maps one signed adapter notch to game ScrollDelta;
    it requires adapter calibration and is not Windows WHEEL_DELTA.
    """
    check()
    pose = _pose(reference)
    if sample_policy not in ('all_recorded_points', 'explicit_indices'):
        raise ValueError('Explicit sample policy required')
    route = list(route)
    if sample_policy == 'explicit_indices':
        if sample_indices is None or len(sample_indices) != len(route):
            raise ValueError('One sample-index list per gesture required')
    elif sample_indices is not None:
        raise ValueError('Unexpected sample-index lists')
    diagnostics = dict(accepted_moves=0, rejected_points=0, accepted_rotations=0,
                       suppressed_rotations=0, wheel_events=0)
    trace = []
    for gi, gesture in enumerate(route):
        check()
        kind = gesture['kind']
        if kind not in ('drag', 'rotate', 'wheel'):
            raise ValueError('Only dye drag, right rotation and wheel records supported')
        points = [(np.asarray(p, dtype=np.float64) if geometry.pixel_mapping is not None else _vector(p))
                  for p in gesture['points']]
        if not points:
            raise ValueError('Press/pivot point required')
        if gesture.get('coordinate_space', 'physical_client_pixels') != 'physical_client_pixels':
            raise ValueError('Physical client pixel coordinates required')
        indices = _sampled_indices(points, sample_policy,
                    None if sample_indices is None else sample_indices[gi])
        start = geometry.local(points[0])
        pivot = geometry.normalized(start)
        if kind == 'wheel':
            if len(points) != 1 or wheel_delta_per_step is None:
                raise ValueError('Wheel requires one pivot and explicit adapter calibration')
            steps = gesture['wheel_steps']
            if type(steps) is not int or abs(steps) > 32:
                raise ValueError('At most 32 whole signed wheel notches per record')
            calibrated = _scalar(wheel_delta_per_step)
            if calibrated == F(0):
                raise ValueError('Nonzero wheel mapping required')
            delta = F(calibrated*(F(1) if steps > 0 else F(-1)))
            zoom = F(F(1)+F(F(settings.scroll_zoom_ratio)*delta))
            for _ in range(abs(steps)):
                check()
                pose = apply_motion_event(pose, pivot, [0, 0], zoom, 0, settings)
                diagnostics['wheel_events'] += 1
                trace.append(dict(gesture=gi, kind=kind, pose=pose))
            continue
        if kind == 'rotate' and gesture.get('right') is not True:
            raise ValueError('Rotation record must explicitly use right button')
        moved, accepted_local, accepted_uv = False, start, pivot
        for pi in indices[1:]:
            check()
            local = geometry.local(points[pi])
            tolerance = F(settings.move_tolerance if moved else settings.move_threshold)
            if _distance(local-accepted_local) < tolerance:
                diagnostics['rejected_points'] += 1
                continue
            current_uv = geometry.normalized(local)
            if kind == 'drag':
                pose = apply_motion_event(pose, pivot, current_uv-accepted_uv, 1, 0,
                                          settings, drag_only=True)
                diagnostics['accepted_moves'] += 1
                delta = 0.
            else:
                delta = virtual_rotation_delta(accepted_uv-pivot, current_uv-pivot)
                pose = apply_motion_event(pose, pivot, [0, 0], 1, delta, settings)
                diagnostics['accepted_rotations' if delta else 'suppressed_rotations'] += 1
            trace.append(dict(gesture=gi, point=pi, kind=kind,
                              rotation_delta=delta, pose=pose))
            moved, accepted_local, accepted_uv = True, local, current_uv
    check()
    return dict(final_pose=pose, diagnostics=diagnostics, trace=trace,
                sample_policy=sample_policy, execution_verified=False,
                game_response_verified=False, release_inertia_modelled=False,
                scope='Conditional recognized-event endpoint; not settled live pose',
                geometry_assumption=('target_awareness_integer_pixels_to_native_viewport_floor_to_UI_local'
                    if geometry.pixel_mapping is not None else 'axis_aligned_affine_screen_to_UI_local'),
                input_coordinate_convention=geometry.input_coordinate_convention,
                between_gesture_assumption='no_unmodelled_inertia_displacement',
                wheel_delta_per_step=wheel_delta_per_step)
