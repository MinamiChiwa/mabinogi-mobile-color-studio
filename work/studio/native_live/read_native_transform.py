"""Bounded sparse native Transform hierarchy observation, without engine calls."""
import math
import struct
import sys

from native_transform_matrix import local_to_world_matrix
from .read_native_rect import SUPPORTED_UNITYPLAYER


def read_native_transform_matrix(reader, managed_transform_address, *, unityplayer_sha256,
                                 max_depth=64, check=lambda: None):
    if unityplayer_sha256 != SUPPORTED_UNITYPLAYER:
        raise ValueError('Unsupported Transform layout build')
    if type(max_depth) is not int or not 1 <= max_depth <= 256:
        raise ValueError('Invalid Transform depth limit')
    reads = {}

    def read(address, size):
        check()
        if type(address) is not int or not 0 < address < 0x7fffffffffff - size:
            raise ValueError('Invalid Transform read address')
        raw = reader.read(address, size)
        if len(raw) != size or reads.setdefault((address, size), raw) != raw:
            raise ValueError('Short or changed Transform read')
        return raw

    def ptr(address):
        value = struct.unpack('<Q', read(address, 8))[0]
        if not value or value % 8:
            raise ValueError('Null/unaligned Transform pointer')
        return value

    cls = ptr(managed_transform_address)
    name = reader.class_name(cls)
    if name not in ('UnityEngine.Transform', 'UnityEngine.RectTransform'):
        raise ValueError('Expected managed Transform/RectTransform')
    native = ptr(managed_transform_address + 0x10)
    data, index = struct.unpack('<Qi', read(native + 0x38, 12))
    if not data or data % 8:
        raise ValueError('Invalid hierarchy data pointer')
    if any(read(data, 12)):
        raise ValueError('Pending Transform job fence')
    capacity = struct.unpack('<i', read(data + 0x10, 4))[0]
    if not 1 <= capacity <= 65536 or not 0 <= index < capacity:
        raise ValueError('Invalid hierarchy capacity/selected index')
    trs = ptr(data + 0x18)
    parents = ptr(data + 0x20)
    natives = ptr(data + 0x30)
    nodes = []
    seen = set()
    cursor = index
    expected_native = native
    while cursor >= 0:
        check()
        if not 0 <= cursor < capacity or cursor in seen or len(nodes) >= max_depth:
            raise ValueError('Cyclic/out-of-range/too deep hierarchy')
        seen.add(cursor)
        node_native = ptr(natives + cursor * 8)
        if node_native != expected_native:
            raise ValueError('Hierarchy native object backlink mismatch')
        back_data, back_index = struct.unpack('<Qi', read(node_native + 0x38, 12))
        if back_data != data or back_index != cursor:
            raise ValueError('Hierarchy data/index backlink mismatch')
        parent = struct.unpack('<i', read(parents + cursor * 4, 4))[0]
        if not -1 <= parent < capacity:
            raise ValueError('Invalid parent index')
        parent_native = struct.unpack('<Q', read(node_native + 0x90, 8))[0]
        if parent == -1:
            if parent_native:
                raise ValueError('Root native parent mismatch')
        elif not parent_native or parent_native % 8:
            raise ValueError('Invalid native parent')
        values = struct.unpack('<12f', read(trs + cursor * 48, 48))
        if not all(math.isfinite(v) for v in values):
            raise ValueError('Nonfinite hierarchy TRS')
        nodes.append(dict(index=cursor, native_address=node_native, parent_index=parent,
                          position=list(values[:3]), quaternion_xyzw=list(values[4:8]), scale=list(values[8:11])))
        cursor = parent
        expected_native = parent_native
    # Compact only the selected ancestry, preserving child-to-root order.
    matrix = local_to_world_matrix([row['position'] for row in nodes],
        [row['quaternion_xyzw'] for row in nodes], [row['scale'] for row in nodes],
        list(range(1, len(nodes))) + [-1], 0, max_depth=max_depth, check=check)
    for (address, size), raw in reads.items():
        check()
        if reader.read(address, size) != raw:
            raise ValueError('Transform hierarchy changed during observation')
    check()
    if reader.class_name(cls) != name:
        raise ValueError('Managed Transform class changed')
    return dict(managed_transform_address=managed_transform_address, native_transform_address=native,
                hierarchy_data_address=data, selected_index=index, capacity_slots=capacity,
                ancestry=nodes, local_to_world_matrix=matrix.tolist(), pending_job_fence=False,
                cache_freshness_verified=False, runtime_measurement_verified=False,
                screen_geometry_available=False, ready_for_input=False,
                scope='Sparse ancestry and native backlinks double-checked; zero fence is not proof of synchronized layout or an atomic frame')
