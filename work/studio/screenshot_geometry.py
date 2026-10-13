"""Offline three-site periodic similarity search using only supplied geometry.

``matrix @ [x, y, 1]`` maps lifted canonical reference coordinates to board
coordinates. Angles follow screen coordinates: positive is clockwise when y
increases downward. Every input site remains available to the search.

The finite pair search is complete if ``exhausted`` is false. For each lifted
pair it uses the nearest periodic third site, then fits a least-squares
orientation-preserving similarity to all three. It does not enumerate every
third site, nor claim to minimize the global minimax residual. The best found
approximation is returned even when its residual is large or time runs out.
"""

from __future__ import annotations

import math
import time

import numpy as np
from scipy.spatial import cKDTree


def _complex(points):
    return points[..., 0] + 1j * points[..., 1]


def _xy(points):
    return np.stack((points.real, points.imag), axis=-1)


def _lattice_offsets(extent, center):
    """Visit the entire bounded square, beginning near the current pose."""
    cx, cy = center
    yield cx, cy
    reach = max(extent + abs(cx), extent + abs(cy))
    for radius in range(1, reach + 1):
        for x in range(cx - radius, cx + radius + 1):
            for y in (cy - radius, cy + radius):
                if -extent <= x <= extent and -extent <= y <= extent:
                    yield x, y
        for y in range(cy - radius + 1, cy + radius):
            for x in (cx - radius, cx + radius):
                if -extent <= x <= extent and -extent <= y <= extent:
                    yield x, y


def solve_joint(sites, period, markers, min_factor=1, max_factor=6,
                current_matrix=None, time_budget=5, limit=24, check=lambda:None,
                fixed_pair=None,candidate_quality=None,endpoint_quality=None):
    """Return ``{candidates, exhausted, elapsed_seconds, evaluated_pairs, ...}``.

    ``sites`` contains three N x 2 arrays, ``markers`` is 3 x 2, and ``period``
    is the square canonical period. Scale factors are absolute scales from
    canonical reference coordinates, including when ``current_matrix`` is set.
    Current pose only affects traversal order, equivalent translation choice,
    and a small tie-breaking movement cost; it never limits the angle search.

    Each candidate includes a 3 x 3 ``matrix`` (also ``desired_matrix``),
    ``scale_factor``, ``angle_degrees``, per-marker ``residuals_screen``, RMS
    ``triple_screen_residual``, ``max_residual``, original canonical ``sites``
    (also ``original_sites``), integer ``lifts``, ``lifted_sites``, input
    ``site_indices``, and movement ``cost``. Score = max_residual + 0.05 * cost.
    No residual acceptance threshold is imposed.
    """
    start = time.perf_counter()
    period, min_factor, max_factor = map(float, (period, min_factor, max_factor))
    time_budget = float(time_budget)
    limit = int(limit)
    if not math.isfinite(period) or period <= 0:
        raise ValueError("period must be finite and positive")
    if not (math.isfinite(min_factor) and math.isfinite(max_factor)
            and 0 < min_factor <= max_factor):
        raise ValueError("scale bounds must be finite and 0 < min_factor <= max_factor")
    if not math.isfinite(time_budget) or time_budget < 0 or limit < 1:
        raise ValueError("time_budget must be nonnegative and limit positive")
    if len(sites) != 3:
        raise ValueError("sites must contain exactly three arrays")
    canonical = []
    for points in sites:
        points = np.asarray(points, dtype=float)
        if points.ndim != 2 or points.shape[1] != 2:
            raise ValueError("each site array must be N x 2")
        if not len(points):
            raise ValueError("site arrays must not be empty")
        if not np.isfinite(points).all():
            raise ValueError("sites must be finite")
        canonical.append(np.mod(points, period))
    markers = np.asarray(markers, dtype=float)
    if markers.shape != (3, 2) or not np.isfinite(markers).all():
        raise ValueError("markers must be finite and 3 x 2")
    m = _complex(markers)
    pairs = [(i, j) for i in range(3) for j in range(i + 1, 3)
             if abs(m[j] - m[i]) > 1e-12]
    if not pairs:
        raise ValueError("at least two markers must be distinct")
    # Fewer site pairs and fewer possible lattice copies reduce work. No pair
    # is discarded geometrically: every triple can be expressed using this pair.
    if fixed_pair is not None and tuple(fixed_pair) not in pairs:
        raise ValueError('fixed_pair must be an ordered pair of distinct markers')
    i, j = tuple(fixed_pair) if fixed_pair is not None else min(pairs, key=lambda ij: (
        len(canonical[ij[0]]) * len(canonical[ij[1]])
        * (1 + math.pi * (abs(m[ij[1]] - m[ij[0]]) / (min_factor * period)) ** 2),
        -abs(m[ij[1]] - m[ij[0]])))
    k = 3 - i - j
    z = [_complex(points) for points in canonical]
    trees = [cKDTree(points, boxsize=period) for points in canonical]
    ratio = (m[k] - m[i]) / (m[j] - m[i])
    mmean = m.mean()
    mcenter = m - mmean
    current_a = current_b = None
    current_inverse = None
    if current_matrix is not None:
        current_matrix = np.asarray(current_matrix, dtype=float)
        if (current_matrix.shape != (3, 3) or not np.isfinite(current_matrix).all()
                or not np.allclose(current_matrix[2], [0, 0, 1])):
            raise ValueError("current_matrix must be a finite affine 3 x 3 matrix")
        current_a = complex((current_matrix[0, 0] + current_matrix[1, 1]) / 2,
                            (current_matrix[1, 0] - current_matrix[0, 1]) / 2)
        if abs(current_a) < 1e-12:
            raise ValueError("current_matrix must have a nonzero similarity scale")
        current_b = complex(current_matrix[0, 2], current_matrix[1, 2])
        current_inverse = (m - current_b) / current_a

    retained = {}
    keep = max(limit * 4, 32)
    evaluated_pairs = examined_pairs = fitted_triples = visited_offsets = 0
    deadline = start + time_budget

    def consume(q, indices, source):
        nonlocal fitted_triples, retained
        q = np.asarray(q, dtype=complex).reshape(-1, 3)
        indices = np.asarray(indices, dtype=int).reshape(-1, 3)
        means = q.mean(axis=1)
        centered = q - means[:, None]
        denom = np.sum(np.abs(centered) ** 2, axis=1)
        valid = denom > 1e-20
        if not np.any(valid):
            return
        q, indices, means, centered, denom = (
            arr[valid] for arr in (q, indices, means, centered, denom))
        if fixed_pair is None:
            a = np.sum(np.conj(centered) * mcenter, axis=1) / denom
        else:
            difference=q[:,j]-q[:,i]
            valid=np.abs(difference)>1e-12
            q,indices,means,centered,denom,difference=(arr[valid] for arr in (q,indices,means,centered,denom,difference))
            if not len(q):return
            a=(m[j]-m[i])/difference
            # Clamping a fixed pair would move its exact anchor sites.
            valid=(np.abs(a)>=min_factor-1e-10)&(np.abs(a)<=max_factor+1e-10)
            q,indices,means,centered,denom,a=(arr[valid] for arr in (q,indices,means,centered,denom,a))
            if not len(q):return
        magnitude = np.abs(a)
        phase = np.divide(a, magnitude, out=np.ones_like(a), where=magnitude > 1e-20)
        a = phase * np.clip(magnitude, min_factor, max_factor)
        b = mmean - a * means if fixed_pair is None else m[i]-a*q[:,i]
        if current_a is not None:
            # A common integer lift represents the same periodic mapping.
            # Choose its translation nearest the supplied current translation.
            common = (b - current_b) / (a * period)
            common = np.rint(common.real) + 1j * np.rint(common.imag)
            q = q + period * common[:, None]
            b = b - a * period * common
            cost = (np.abs(np.log(np.abs(a) / abs(current_a)))
                    + np.abs(np.angle(a / current_a))
                    + np.abs(b - current_b) / (period * abs(current_a)))
        else:
            cost = np.zeros(len(q))
        residuals = np.abs(a[:, None] * q + b[:, None] - m)
        maximum = residuals.max(axis=1)
        scores = maximum + 0.05 * cost
        qualities=(np.column_stack((scores,maximum,cost)) if candidate_quality is None else
                   np.asarray(candidate_quality(indices,residuals,cost),float))
        if endpoint_quality is not None:
            endpoints=(m[None,:]-b[:,None])/a[:,None]
            qualities=np.asarray(endpoint_quality(_xy(endpoints),np.abs(a),indices,residuals,cost),float)
        if qualities.ndim!=2 or len(qualities)!=len(q):raise ValueError('Invalid candidate quality array')
        fitted_triples += len(q)
        count = min(keep, len(q))
        selected = np.lexsort(qualities.T[::-1])[:count]
        for pos in selected:
            alpha, beta = a[pos], b[pos]
            angle = math.degrees(math.atan2(alpha.imag, alpha.real))
            key = (round(abs(alpha), 8), round(angle, 7),
                   round(beta.real, 6), round(beta.imag, 6))
            quality=tuple(qualities[pos])
            if key in retained and tuple(retained[key]['geometry_rank']) <= quality:
                continue
            original = np.array([canonical[n][indices[pos, n]] for n in range(3)])
            lifted = _xy(q[pos])
            matrix = np.array([[alpha.real, -alpha.imag, beta.real],
                               [alpha.imag, alpha.real, beta.imag], [0, 0, 1]], float)
            retained[key] = {
                "matrix": matrix, "desired_matrix": matrix,
                "scale_factor": float(abs(alpha)), "angle_degrees": angle,
                "residuals_screen": residuals[pos].copy(),
                "triple_screen_residual": float(np.sqrt(np.mean(residuals[pos] ** 2))),
                "max_residual": float(maximum[pos]),
                "triple_screen_max": float(maximum[pos]),
                "original_sites": original, "sites": original,
                "lifts": np.rint((lifted - original) / period).astype(np.int64),
                "lifted_sites": lifted, "site_indices": indices[pos].copy(),
                "cost": float(cost[pos]), "score": float(scores[pos]), "source": source,
                'geometry_rank':quality,
            }
            if fixed_pair is not None:retained[key]['fixed_exact_pair']=list(fixed_pair)
        if len(retained) > keep * 2:
            ordered = sorted(retained.items(), key=lambda item: item[1]['geometry_rank'])
            retained = dict(ordered[:keep])

    def nearest_third(first, second):
        prediction = first + ratio * (second - first)
        _, index = trees[k].query(np.mod(_xy(prediction), period))
        original = z[k][index]
        lift = (prediction - original) / period
        lifted = original + period * (np.rint(lift.real) + 1j * np.rint(lift.imag))
        return lifted, index

    # Seed a bounded-scale approximation before the timed exhaustive pair search,
    # so a deadline never erases the nearest candidate found so far.
    if current_inverse is not None:
        seed, seed_indices = [], []
        for n in range(3):
            _, index = trees[n].query(np.mod(_xy(current_inverse[n]), period))
            lift = (current_inverse[n] - z[n][index]) / period
            seed.append(z[n][index] + period * (round(lift.real) + 1j * round(lift.imag)))
            seed_indices.append(index)
        consume([seed], [seed_indices], "current_seed")
    first, second = z[i][0], z[j][0]
    target = first + (m[j] - m[i]) / math.sqrt(min_factor * max_factor)
    lift = (target - second) / period
    second += period * (round(lift.real) + 1j * round(lift.imag))
    if abs(second - first) < 1e-12:
        second += period
    third, third_index = nearest_third(first, second)
    seed = np.empty((1, 3), complex)
    seed_indices = np.zeros((1, 3), int)
    seed[0, [i, j, k]] = [first, second, third]
    seed_indices[0, k] = third_index
    consume(seed, seed_indices, "fallback_seed")

    distance = abs(m[j] - m[i])
    rmin, rmax = distance / max_factor, distance / min_factor
    extent = int(math.ceil(rmax / period)) + 1
    center = (0, 0)
    first_order = np.arange(len(z[i]))
    second_order = np.arange(len(z[j]))
    if current_inverse is not None:
        delta = (current_inverse[j] - current_inverse[i]) / period
        center = (int(np.clip(round(delta.real), -extent, extent)),
                  int(np.clip(round(delta.imag), -extent, extent)))
        for n, order in ((i, first_order), (j, second_order)):
            delta = z[n] - current_inverse[n]
            wrapped = (delta.real + period / 2) % period - period / 2
            wrapped_y = (delta.imag + period / 2) % period - period / 2
            order[:] = np.argsort(wrapped ** 2 + wrapped_y ** 2, kind="stable")
    seconds = z[j][second_order]
    chunk = max(1, 16384 // len(seconds))
    exhausted = False
    for offset_x, offset_y in _lattice_offsets(extent, center):
        check()
        if time.perf_counter() >= deadline:
            exhausted = True
            break
        # Differences of two canonical coordinates lie in (-period, period).
        # This bound includes all copies whose distance can satisfy the annulus.
        nearest_x = max(0, (abs(offset_x) - 1) * period)
        nearest_y = max(0, (abs(offset_y) - 1) * period)
        if nearest_x ** 2 + nearest_y ** 2 > rmax ** 2 + 1e-9:
            continue
        farthest_x = (abs(offset_x) + 1) * period
        farthest_y = (abs(offset_y) + 1) * period
        if farthest_x ** 2 + farthest_y ** 2 < rmin ** 2 - 1e-9:
            continue
        visited_offsets += 1
        offset = period * complex(offset_x, offset_y)
        for begin in range(0, len(first_order), chunk):
            check()
            if time.perf_counter() >= deadline:
                exhausted = True
                break
            first_indices = first_order[begin:begin + chunk]
            differences = seconds[None, :] + offset - z[i][first_indices, None]
            norms = np.abs(differences)
            valid = (norms >= rmin - 1e-10) & (norms <= rmax + 1e-10) & (norms > 1e-12)
            examined_pairs += differences.size
            rows, columns = np.nonzero(valid)
            if not len(rows):
                continue
            evaluated_pairs += len(rows)
            first_values = z[i][first_indices[rows]]
            second_values = seconds[columns] + offset
            third_values, third_indices = nearest_third(first_values, second_values)
            q = np.empty((len(rows), 3), complex)
            q[:, i], q[:, j], q[:, k] = first_values, second_values, third_values
            indices = np.empty((len(rows), 3), int)
            indices[:, i] = first_indices[rows]
            indices[:, j] = second_order[columns]
            indices[:, k] = third_indices
            consume(q, indices, "search")
        if exhausted:
            break
    candidates = sorted(retained.values(), key=lambda candidate:candidate['geometry_rank'])[:limit]
    return {
        "candidates": candidates, "exhausted": exhausted,
        "elapsed_seconds": time.perf_counter() - start,
        "evaluated_pairs": evaluated_pairs, "examined_pairs": examined_pairs,
        "fitted_triples": fitted_triples, "visited_offsets": visited_offsets,
        "anchor_indices": (i, j, k), "site_counts": tuple(map(len, canonical)),
        "search_method": "all feasible lifted pairs, nearest periodic third, "+
            ("fixed exact anchors" if fixed_pair is not None else "three-point fit"),
    }
