"""Offline float32 equivalent of UnityPlayer's TRS hierarchy arithmetic.

Input arrays must already belong to the selected Transform. No engine cache
refresh, synchronization, object binding, or Canvas projection is performed.
Quaternions are consumed as stored, without renormalization.
"""
from numbers import Integral

import numpy as np


def _integer(value):
    return isinstance(value, Integral) and not isinstance(value, (bool, np.bool_))


def _columns(position, q, scale):
    x, y, z, _ = q
    a = q[[1, 0, 3, 1]]
    b = q[[3, 2, 1, 3]]
    c = q[[2, 3, 0, 2]]
    cx = ((y * np.array([-2, 2, -2, 0], np.float32)) * a
          + (z * np.array([-2, 2, 2, 0], np.float32)) * c)
    cy = ((z * np.array([-2, -2, 2, 0], np.float32)) * b
          + (x * np.array([2, -2, 2, 0], np.float32)) * a)
    cz = ((x * np.array([2, -2, -2, 0], np.float32)) * c
          + (y * np.array([2, 2, -2, 0], np.float32)) * b)
    cx = (cx + np.array([1, 0, 0, 0], np.float32)) * scale[0]
    cy = (cy + np.array([0, 1, 0, 0], np.float32)) * scale[1]
    cz = (cz + np.array([0, 0, 1, 0], np.float32)) * scale[2]
    return np.array([cx, cy, cz, [*position, 0]], dtype=np.float32)


def local_to_world_matrix(positions, quaternions_xyzw, scales, parents, index,
                          *, max_depth=64, check=lambda: None):
    check()
    if not _integer(max_depth) or not 1 <= max_depth <= 256:
        raise ValueError('Invalid hierarchy depth limit')
    with np.errstate(over='ignore', invalid='ignore'):
        p = np.asarray(positions, dtype=np.float32)
        q = np.asarray(quaternions_xyzw, dtype=np.float32)
        s = np.asarray(scales, dtype=np.float32)
    if p.ndim != 2 or p.shape[1] != 3 or not 1 <= len(p) <= 65536:
        raise ValueError('Invalid positions')
    n = len(p)
    if q.shape != (n, 4) or s.shape != (n, 3) or not all(np.isfinite(a).all() for a in (p, q, s)):
        raise ValueError('Invalid TRS arrays')
    if len(parents) != n or any(not _integer(v) or not -1 <= v < n for v in parents):
        raise ValueError('Invalid parent indices')
    if not _integer(index) or not 0 <= index < n:
        raise ValueError('Invalid selected index')
    ancestry = []
    seen = set()
    cursor = index
    while cursor >= 0:
        check()
        if cursor in seen or len(ancestry) >= max_depth:
            raise ValueError('Cyclic or too deep hierarchy')
        seen.add(cursor)
        ancestry.append(cursor)
        cursor = parents[cursor]
    with np.errstate(over='ignore', invalid='ignore'):
        result = _columns(p[index], q[index], s[index])
        for parent in ancestry[1:]:
            check()
            basis = _columns(p[parent], q[parent], s[parent])
            # Match SIMD addition grouping; ordinary matrix multiplication
            # may accumulate in a different order or fuse multiply/add.
            result = (basis[0] * result[:, 0, None]
                      + (basis[1] * result[:, 1, None] + basis[2] * result[:, 2, None]))
            result[3] = result[3] + basis[3]
        result = result.T.copy()
    if not np.isfinite(result).all():
        raise ValueError('Nonfinite hierarchy result')
    result[3] = [0, 0, 0, 1]
    return result
