"""Shared actual-layout contract for two- and three-fragment dye boards."""
import copy
import numpy as np

SUPPORTED_REGION_COUNTS = (2, 3)


def region_count(value):
    if type(value) is not int or value not in SUPPORTED_REGION_COUNTS:
        raise ValueError('Actual dye region count must be two or three')
    return value


def rule_region_count(rules):
    if not isinstance(rules, (list, tuple)) or any(not isinstance(r, dict) for r in rules):
        raise ValueError('Dictionary target rules required')
    return region_count(len(rules))


def session_region_count(session):
    """Infer old captures, while rejecting contradictory explicit layout data."""
    if not isinstance(session, dict):
        raise ValueError('Dye session required')
    pixels = session.get('pixels')
    if not isinstance(pixels, (list, tuple)):
        raise ValueError('Captured dye fragments required')
    count = region_count(len(pixels))
    for key in ('region_count', 'actual_count'):
        if key in session and region_count(session[key]) != count:
            raise ValueError('Actual dye count differs from captured fragments')
    points = np.asarray(session.get('picker_uv'), dtype=float)
    if points.shape != (count, 2) or not np.isfinite(points).all():
        raise ValueError('Picker count differs from captured fragments')
    if (not np.allclose(points[:, 0], (np.arange(count) + .5) / count, rtol=0., atol=1e-7)
            or np.any(points[:, 1] < 0.) or np.any(points[:, 1] > 1.)):
        raise ValueError('Picker positions differ from actual dye layout')
    return count


def bind_region_rules(rules, actual_count):
    """Own the existing UI slots that are present in this actual board."""
    count = region_count(actual_count)
    supplied = rule_region_count(rules)
    if supplied < count:
        raise ValueError('Target rules omit an actual dye region')
    owned = copy.deepcopy(list(rules[:count]))
    if not any(r.get('enabled') for r in owned):
        raise ValueError('No enabled target remains on the actual dye board')
    return owned


def validate_region_rules(session, rules):
    count = session_region_count(session)
    if rule_region_count(rules) != count or not any(r.get('enabled') for r in rules):
        raise ValueError('Enabled target rules must match the actual dye region count')
    return count
