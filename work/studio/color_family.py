"""Product heuristics for preserving every enabled region's colour family.

These LCh limits rank compromises; they are not perceptual standards, game
response bounds, or replacements for the user's exact/Delta E acceptance rule.
Zero means within the family envelope. Outside it, worst-region excess wins
before averages so a severe mismatch cannot hide behind two good regions.
"""
import numpy as np
import cv2
from vision import lab, rgb


NEUTRAL_CHROMA = 12.
NEUTRAL_LIGHTNESS_RANGE = 20.
COLOR_LIGHTNESS_RANGE = 25.
HUE_RANGE_DEGREES = 35.
RGB_HUE_RANGE_DEGREES = 20.
MIN_CHROMA_RATIO = .4
MAX_CHROMA_RATIO = 1.8


def family_penalties(values, rule):
    """Vectorized nonnegative envelope excess; any allowed target can match."""
    values = np.asarray(values).reshape(-1, 3)
    targets = [rgb(value) for value in rule['colors']]
    if not targets:
        raise ValueError('Enabled region requires target colors')
    measured = lab(values)
    # Lab hue is strongly compressed between saturated sRGB blue and purple.
    # Keep an independent RGB hue envelope so purple/magenta cannot be ranked
    # as a zero-penalty blue compromise merely by losing saturation.
    rgb_hue = cv2.cvtColor((values.astype(np.float32)/255).reshape(-1,1,3),
                          cv2.COLOR_RGB2HSV).reshape(-1,3)[:,0]
    target_hues = cv2.cvtColor((np.asarray(targets,np.float32)/255).reshape(-1,1,3),
                              cv2.COLOR_RGB2HSV).reshape(-1,3)[:,0]
    chroma = np.linalg.norm(measured[:, 1:], axis=1)
    hue = np.degrees(np.arctan2(measured[:, 2], measured[:, 1]))
    best = np.full(len(values), np.inf)
    for target,target_rgb_hue in zip(lab(targets),target_hues):
        target_chroma = float(np.linalg.norm(target[1:]))
        if target_chroma <= NEUTRAL_CHROMA:
            # White/grey/black have no dependable hue. Preserve lightness
            # and low chroma instead; grey must not count as a blue match.
            excess = np.maximum(
                np.abs(measured[:, 0] - target[0]) / NEUTRAL_LIGHTNESS_RANGE - 1.,
                chroma / max(18., target_chroma + 6.) - 1.)
        else:
            target_hue = np.degrees(np.arctan2(target[2], target[1]))
            hue_distance = np.abs((hue - target_hue + 180.) % 360. - 180.)
            low = max(8., MIN_CHROMA_RATIO * target_chroma)
            high = max(target_chroma + 20., MAX_CHROMA_RATIO * target_chroma)
            # Hue is undefined at zero chroma. Its mismatch is handled by
            # the chroma deficit, without adding an arbitrary hue penalty.
            hue_excess = np.where(chroma > 1., hue_distance / HUE_RANGE_DEGREES - 1., 0.)
            rgb_hue_distance = np.abs((rgb_hue-target_rgb_hue+180.)%360.-180.)
            rgb_hue_excess = np.where(chroma > 1., rgb_hue_distance/RGB_HUE_RANGE_DEGREES-1., 0.)
            excess = np.maximum.reduce((hue_excess,rgb_hue_excess,
                (low - chroma) / low, chroma / high - 1.,
                np.abs(measured[:, 0] - target[0]) / COLOR_LIGHTNESS_RANGE - 1.))
        best = np.minimum(best, np.maximum(excess, 0.))
    return best


def family_priority(colors, rules):
    """Return worst/mean excess and per-region excess, excluding disabled ones."""
    enabled = [i for i, rule in enumerate(rules) if rule.get('enabled')]
    penalties = [None] * len(rules)
    for i in enabled:
        penalties[i] = family_penalties(colors[i], rules[i])
    return (np.maximum.reduce([penalties[i] for i in enabled]),
            np.mean([penalties[i] for i in enabled], axis=0), penalties)


def family_fields(maximum, average, penalties, index):
    return dict(family_consistent=bool(maximum[index] <= 1e-7),
                family_maximum=float(maximum[index]), family_average=float(average[index]),
                family_penalties=[float(value[index]) if value is not None else None
                                  for value in penalties])
