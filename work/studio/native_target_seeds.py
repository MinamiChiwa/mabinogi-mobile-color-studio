"""Target-colored subpixel lattice seeds; not a complete interpolation search."""
from dye_regions import validate_region_rules
import math
import time
import numpy as np
from vision import rgb, lab
from native_palette_model import picker_view_uv, sample_cpu, color32
from native_palette_scoring import _pose
from region_priority import priority_indices


def _inverse(uv):
    value = np.asarray(uv, dtype=np.float64).copy()
    for _ in range(2):
        value[1] -= math.sin(4 * math.pi * value[0]) / (4 * math.pi)
        value[0] -= math.sin(4 * math.pi * value[1]) / (4 * math.pi)
    return value


def target_seed_poses(session, rules, *, scales=(1.,), rotations_degrees=(0.,),
                      pixels_per_region=16, period_offsets=((0, 0),), reference=None,
                      max_candidates=10000, time_budget_seconds=5., clock=time.monotonic,
                      check=lambda: None, subpixel_fractions=(0.,)):
    """Invert near-target sampled texture coordinates to shared poses.

    Period offsets are integer canonical-domain copies around the nearest
    reference phase. Seed inverse uses double arithmetic; every final proposal
    MUST be rescored by the original-order CPU picker and then action model.
    """
    scales, rotations = tuple(scales), tuple(rotations_degrees)
    offsets = tuple(tuple(p) for p in period_offsets)
    fractions = tuple(float(v) for v in subpixel_fractions)
    if not fractions or len(fractions) > 8 or not all(math.isfinite(v) and 0 <= v < 1 for v in fractions):
        raise ValueError('Subpixel fractions must be finite and in [0,1)')
    if not scales or not rotations or len(scales) > 100 or len(rotations) > 100 or not np.isfinite(scales + rotations).all() or min(scales) <= 0:
        raise ValueError('Finite positive scales and finite angles required')
    if not offsets or len(offsets) > 100 or any(len(p) != 2 or any(type(v) is not int for v in p) for p in offsets):
        raise ValueError('Integer period offsets required')
    if type(pixels_per_region) is not int or not 1 <= pixels_per_region <= 1000:
        raise ValueError('Invalid pixel seed limit')
    if type(max_candidates) is not int or not 1 <= max_candidates <= 100000 or not math.isfinite(time_budget_seconds) or time_budget_seconds <= 0:
        raise ValueError('Invalid generation budget')
    count = validate_region_rules(session, rules)
    reference = _pose(session['initial_pose'] if reference is None else reference)
    start = clock()
    end = start + time_budget_seconds
    seeds, seen = [], set()
    reason = 'seeds_exhausted'

    class Expired(Exception):
        pass

    def guard():
        check()
        if clock() >= end:
            raise Expired()

    try:
        ordered=priority_indices(rules)
        for region in range(len(rules)) if ordered is None else ordered:
            rule=rules[region]
            guard()
            if not rule['enabled']:
                continue
            if not rule['colors']:
                raise ValueError('Enabled rule has no targets')
            pixels = session['pixels'][region]
            height, width = pixels.shape[:2]
            yy, xx = np.indices((height, width))
            choices = []
            for fy in fractions:
                for fx in fractions:
                    guard()
                    uv_samples = np.stack(((xx + .5 + fx) / width,
                                           (height - yy - .5 + fy) / height), axis=-1).reshape(-1, 2).astype(np.float32)
                    flat = color32(sample_cpu(pixels, uv_samples, session['color_preserve_ratio']) / np.float32(255))
                    losses = np.full(len(flat), np.inf)
                    for target in rule['colors']:
                        guard()
                        target_rgb = np.asarray(rgb(target))
                        if rule['exact']:
                            distance = np.max(np.abs(flat.astype(float) - target_rgb), axis=1)
                        else:
                            distance = np.linalg.norm(lab(flat) - lab([target_rgb])[0], axis=1)
                        losses = np.minimum(losses, distance)
                    guard()
                    selected = np.argsort(losses, kind='stable')[:pixels_per_region]
                    choices.extend((float(losses[index]), int(index), fx, fy, uv_samples[index]) for index in selected)
            choices.sort(key=lambda row: (row[0], row[1], row[2], row[3]))
            z_reference = picker_view_uv(region, count, session['picker_uv'][region][1], **reference).astype(float)
            for loss, index, fx, fy, uv in choices[:pixels_per_region]:
                guard()
                y, x = divmod(int(index), width)
                z = _inverse(uv)
                nearest = np.rint(z_reference - z)
                for scale in scales:
                    for angle in rotations:
                        theta = math.radians(angle)
                        rotation = np.array([[math.cos(theta), -math.sin(theta)],
                                             [math.sin(theta), math.cos(theta)]])
                        for offset in offsets:
                            guard()
                            canonical = z + nearest + offset
                            position = np.asarray(session['picker_uv'][region]) - .5 - scale * (rotation @ canonical)
                            pose = _pose(dict(position=position, scale=scale, rotation_degrees=angle))
                            key = tuple((*pose['position'], pose['scale'], pose['rotation_degrees']))
                            if key in seen:
                                continue
                            if len(seeds) >= max_candidates:
                                reason = 'candidate_limit'
                                raise Expired()
                            seen.add(key)
                            seeds.append(dict(native_pose=pose, anchor_region=region,
                                              pixel_xy=[x, y], subpixel_fraction=[fx, fy],
                                              sampled_color_distance=loss))
    except Expired:
        if reason == 'seeds_exhausted':
            reason = 'deadline'
    return dict(poses=[s['native_pose'] for s in seeds], seeds=seeds,
                generated=len(seeds), stop_reason=reason, complete=reason == 'seeds_exhausted',
                elapsed_seconds=max(0., clock() - start),
                coverage='explicit subpixel sample lattice only; unsampled interpolated targets and other phases may be missed',
                input_reachability='unverified')
