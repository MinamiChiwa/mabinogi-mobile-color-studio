"""Target-aware compromise preference, separate from HEX/Delta-E acceptance.

The original RGB and CIELAB Delta E remain unchanged. Chromatic targets add
continuous hue/saturation penalties; neutral targets retain Delta E exactly.
This preference score is not a new tolerance unit or a certified game result.
"""
from functools import lru_cache
import colorsys
import math
import numpy as np
from vision import lab, normalize_hex, rgb, error

MATCHING_POLICY = 'hue-saturation-v1'
HUE_WEIGHT = 60.
SATURATION_WEIGHT = 25.


def _hsv(values):
    values = np.asarray(values, dtype=np.float64)
    red, green, blue = np.moveaxis(values, -1, 0)
    maximum = np.maximum(np.maximum(red,green),blue)
    minimum = np.minimum(np.minimum(red,green),blue)
    chroma = maximum - minimum
    divisor = np.where(chroma > 0, chroma, 1.)
    hue = np.where(maximum == red, (green-blue)/divisor,
          np.where(maximum == green, (blue-red)/divisor+2., (red-green)/divisor+4.))
    hue = np.where(chroma > 0, (hue/6.) % 1., 0.)
    saturation = np.divide(chroma, maximum, out=np.zeros_like(chroma), where=maximum > 0)
    return hue, saturation, chroma/255.


@lru_cache(maxsize=512)
def _targets(codes):
    values = np.asarray([rgb(code) for code in codes])
    return lab(values), _hsv(values)


def matching_distances(values, rule, *, color_lab=None, base_distances=None):
    """One score per whole RGB sample, minimizing whole-target scores only.

    Alternative targets must never donate different components to a synthetic
    target. The best Delta-E target need not be the best preference target.
    """
    values = np.asarray(values).reshape(-1, 3)
    if not len(values):
        return np.empty(0)
    targets = tuple(normalize_hex(code) for code in rule['colors'])
    if not targets:
        return np.full(len(values), np.inf)
    target_lab, (target_hue, target_saturation, target_chroma) = _targets(targets)
    actual_lab = lab(values) if color_lab is None else np.asarray(color_lab)
    result = np.full(len(values), np.inf)
    chromatic = bool(np.any(target_chroma > 0))
    hue, saturation, _ = _hsv(values) if chromatic else (None, None, None)
    for i, target in enumerate(target_lab):
        score = (np.asarray(base_distances,dtype=float).copy() if len(target_lab)==1 and base_distances is not None
                 else np.linalg.norm(actual_lab - target, axis=1).astype(float))
        if target_chroma[i] > 0:
            # Circular chord distance has no discontinuity at red's 0/360 edge.
            chord = 2.*np.abs(np.sin(np.pi*(hue-target_hue[i])))
            score += target_chroma[i]*(HUE_WEIGHT*saturation*chord +
                SATURATION_WEIGHT*np.abs(saturation-target_saturation[i]))
        result = np.minimum(result, score)
    return np.where(np.isfinite(result) & (result >= 0), result, np.inf)


@lru_cache(maxsize=8192)
def _score(code, targets):
    if code in targets:
        return 0.
    hue, saturation, _ = _code_hsv(code)
    best = math.inf
    for target in targets:
        th, ts, chroma = _code_hsv(target)
        value = error(code, [target], False)
        if chroma:
            value += chroma*(HUE_WEIGHT*saturation*2*abs(math.sin(math.pi*(hue-th))) +
                             SATURATION_WEIGHT*abs(saturation-ts))
        best = min(best, value)
    return best


@lru_cache(maxsize=8192)
def _code_hsv(code):
    values = tuple(v/255. for v in rgb(code))
    hue, saturation, _ = colorsys.rgb_to_hsv(*values)
    return hue, saturation, max(values)-min(values)


def matching_score(code, rule):
    if code is None:
        return float('inf')
    return _score(normalize_hex(code), tuple(normalize_hex(c) for c in rule['colors']))


def has_chromatic_target(rule):
    return any(_targets(tuple(normalize_hex(c) for c in rule['colors']))[1][2] > 0)


def matching_summary(codes, rules):
    scores = [matching_score(c, rule) for c, rule in zip(codes, rules) if rule['enabled']]
    return (max(scores), sum(scores)/len(scores)) if scores else (float('inf'), float('inf'))
