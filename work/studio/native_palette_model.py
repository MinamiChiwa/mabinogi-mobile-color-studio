"""Pure CPU model of the game's dye-palette color query.

This module is deliberately independent of screenshots, UI, Windows input and
the live process.  ``pixels`` are saved top-down RGB arrays; the game's raw
palette rows are addressed bottom-up and UV coordinates repeat periodically.
"""

import numpy as np
import math

_K = np.float32(12.566370964050293)
_A = np.float32(1.0) / _K


def view_uv(uv, position, scale, rotation_degrees):
    """Map screen-normalized UV to the shared rotated view coordinates."""
    scale = np.float32(scale)
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError("scale must be finite and positive")
    r = (np.asarray(uv, dtype=np.float32) - np.asarray(position, dtype=np.float32) - np.float32(.5)) / scale
    angle = np.float32(-rotation_degrees) * np.float32(np.pi) / np.float32(180)
    c, s = np.cos(angle), np.sin(angle)
    return np.stack((r[..., 0] * c - r[..., 1] * s,
                     r[..., 0] * s + r[..., 1] * c), axis=-1)


def distort_uv(uv):
    """Apply the two alternating sinusoidal shear passes."""
    result = np.asarray(uv, dtype=np.float32).copy()
    for _ in range(2):
        result[..., 0] += np.sin(_K * result[..., 1]) * _A
        result[..., 1] += np.sin(_K * result[..., 0]) * _A
    return result


def picker_view_uv(index, count, picker_y, position, scale, rotation_degrees):
    """Original CPU picker arithmetic order, distinct from display UV math."""
    if type(index) is not int or type(count) is not int or not 0 <= index < count <= 32:
        raise ValueError('Invalid fragment index/count')
    f = np.float32
    position = np.asarray(position, dtype=np.float32)
    if position.shape != (2,) or not np.isfinite(position).all() or not np.isfinite([scale, rotation_degrees, picker_y]).all() or scale <= 0:
        raise ValueError('Invalid picker pose')
    centre = f(.5) + position
    inv_count = f(1) / f(count)
    x = f(f(-centre[0] + f(inv_count * f(.5))) + f(f(index) * inv_count))
    y = f(-centre[1] + f(picker_y))
    inv_scale = f(1) / f(scale)
    x, y = f(x * inv_scale), f(y * inv_scale)
    angle = f(f(f(-rotation_degrees) * f(np.pi)) / f(180))
    c, s = f(math.cos(float(angle))), f(math.sin(float(angle)))
    return np.array([f(f(c * x) - f(s * y)), f(f(c * y) + f(s * x))], np.float32)


def distort_cpu_uv(uv):
    """CPU sin primitive rounding, independently checked against native code."""
    result = np.asarray(uv, dtype=np.float32).copy()
    if result.shape != (2,) or not np.isfinite(result).all():
        raise ValueError('One finite UV required')
    f = np.float32
    for _ in range(2):
        result[0] = f(result[0] + f(f(math.sin(float(f(f(result[1] + result[1]) * f(_K / 2))))) / _K))
        result[1] = f(result[1] + f(f(math.sin(float(f(f(result[0] + result[0]) * f(_K / 2))))) / _K))
    return result


def sample_cpu(pixels, uv, color_preserve_ratio):
    """Evaluate the game's CPU color-preserving bilinear query.

    The verified native domain is ``0 <= p < 1``.  Native p=1 boundary cases
    can produce non-finite values, so callers must not silently approximate it.
    """
    p = float(color_preserve_ratio)
    if not np.isfinite(p) or not 0 <= p < 1:
        raise ValueError("color_preserve_ratio must be finite and in [0, 1)")
    texture = np.asarray(pixels)
    if texture.ndim != 3 or texture.shape[2] != 3:
        raise ValueError("pixels must have shape (height, width, 3)")
    height, width = texture.shape[:2]
    if not height or not width:
        raise ValueError("pixels must be non-empty")
    coordinates = (np.asarray(uv, dtype=np.float32) % np.float32(1)) * np.array([width, height], np.float32) - np.float32(.5)
    integer = np.floor(coordinates).astype(np.int64)
    fraction = coordinates - integer
    q = np.sqrt(np.float32(p))
    fraction = np.clip((fraction - q / 2) / (1 - q), 0, 1).astype(np.float32)
    x, y = integer[..., 0], integer[..., 1]
    top_left = texture[height - 1 - y % height, x % width].astype(np.float32)
    top_right = texture[height - 1 - y % height, (x + 1) % width].astype(np.float32)
    bottom_left = texture[height - 1 - (y + 1) % height, x % width].astype(np.float32)
    bottom_right = texture[height - 1 - (y + 1) % height, (x + 1) % width].astype(np.float32)
    tx, ty = fraction[..., 0, None], fraction[..., 1, None]
    return (top_left * (1 - tx) + top_right * tx) * (1 - ty) + (bottom_left * (1 - tx) + bottom_right * tx) * ty


def color32(values):
    """Convert normalized channels with the native float32 rounding rule."""
    values = np.asarray(values, dtype=np.float32)
    if not np.all(np.isfinite(values)):
        raise ValueError("color values must be finite")
    scaled = np.clip(values, 0, 1) * np.float32(255)
    fraction, whole = np.modf(scaled.astype(np.float64))
    ties = fraction == .5
    ordinary = np.floor(scaled + np.float32(.5))
    even = whole + (whole.astype(np.int64) % 2)
    return np.where(ties, even, ordinary).astype(np.uint8)


def predict_hex(pixels, uv, color_preserve_ratio=0.0):
    """Return the game-style six-digit HEX for one normalized UV query."""
    color = sample_cpu(pixels, np.asarray(uv, dtype=np.float32), color_preserve_ratio)
    channels = color32(color / np.float32(255))
    if channels.ndim != 1 or channels.shape[0] != 3:
        raise ValueError("predict_hex expects one UV coordinate")
    return "#%02X%02X%02X" % tuple(int(value) for value in channels)
