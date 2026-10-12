"""Shared region order for Exact, Similar, predictions and measured results."""
import math
import numpy as np
from vision import error, normalize_hex, rgb
from dye_regions import rule_region_count

PRIORITY_DELTA_E_BIN = .5


def priority_indices(rules):
    rule_region_count(rules)
    if not any('priority' in r for r in rules):
        return None
    enabled = [i for i, r in enumerate(rules) if r.get('enabled')]
    values = [rules[i].get('priority') for i in enabled]
    if any(type(v) is not int or not 1 <= v <= 3 for v in values) or len(set(values)) != len(values):
        raise ValueError('Enabled region priorities must be unique integers from 1 to 3')
    return sorted(enabled, key=lambda i: rules[i]['priority'])


def priority_components(codes, rules, deltas=None):
    """Interleave satisfaction and half-Delta-E bins in user region order.

    All-region acceptance remains outside this tuple. A satisfied Similar
    region releases its error priority to later regions. Bins rank only;
    they never relax exact HEX or Similar tolerance acceptance.
    """
    order = priority_indices(rules)
    if order is None:
        return None
    components = []
    for i in order:
        rule = rules[i]; color = codes[i]
        valid = color is not None
        delta = error(color, rule['colors'], False) if valid and deltas is None else (deltas[i] if valid else math.inf)
        delta = float(delta) if delta is not None and math.isfinite(delta) and delta >= 0 else math.inf
        valid = valid and math.isfinite(delta)
        hit = (normalize_hex(color) in [normalize_hex(c) for c in rule['colors']] if valid and rule['exact']
               else valid and delta <= float(rule['tolerance']))
        bucket = 0 if hit else math.floor(delta / PRIORITY_DELTA_E_BIN) if math.isfinite(delta) else math.inf
        components.extend((int(not hit), bucket))
    return tuple(components)


def vector_priority_components(colors, distances, rules):
    order = priority_indices(rules)
    if order is None:
        return None
    components = []
    for i in order:
        raw = np.asarray(distances[i], float)
        values = np.where(np.isfinite(raw) & (raw >= 0), raw, np.inf)
        if rules[i]['exact']:
            targets = np.asarray([rgb(c) for c in rules[i]['colors']])
            hit = np.isfinite(values) & np.any(np.all(np.asarray(colors[i])[:, None, :] == targets, axis=-1), axis=1)
        else:
            hit = values <= float(rules[i]['tolerance'])
        components.extend((~hit, np.where(hit, 0., np.floor(values / PRIORITY_DELTA_E_BIN))))
    return np.stack(components, axis=1)


def priority_fields(codes, deltas, rules):
    components = priority_components(codes, rules, deltas)
    return {} if components is None else dict(region_priority=list(components))
