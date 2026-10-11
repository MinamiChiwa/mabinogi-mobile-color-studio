"""Offline scanner throughput comparison; never opens or reads a process.

Run: python -m native_live.benchmark_dye_scan --mib 512 --output FILE.json
Both paths consume the same immutable 8 MiB chunk for each shape. Repetition
keeps peak fixture memory small. This measures search/census CPU, excluding
ReadProcessMemory, region enumeration in Windows, and real object inspection.
"""
import argparse
import json
import struct
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from . import scan_live_dye as scanning


CHUNK = 8 * 1024 * 1024
CLASS = 0x19115BA8C80


class OfflineHeap:
    def __init__(self, chunk, repeats):
        self.chunk = chunk; self.payload = chunk + chunk[:8]
        self.size = len(chunk)*repeats; self.base = 0x10000

    def regions(self):
        yield SimpleNamespace(BaseAddress=self.base, RegionSize=self.size,
            State=0x1000, Type=0x20000, Protect=4)

    def read(self, address, size):
        if size == CHUNK+8: return self.payload
        if size == CHUNK: return self.chunk
        raise ValueError('Unexpected offline chunk read')


def _run(chunk, repeats, *, aligned):
    reader = OfflineHeap(chunk, repeats)
    census = scanning.IncrementalDyeScan(reader, CLASS, clock=time.perf_counter)
    if not aligned:
        census.aligned_search_min_bytes = float('inf')
        census.search_pattern = census.pattern
        census.buffer_search_pattern = census.pattern
    def inspect(reader, address, cls):
        return dict(address=hex(address), capture_eligible=False)
    started = time.perf_counter()
    deadline = time.perf_counter()+120.
    with patch.object(scanning, 'inspect', side_effect=inspect):
        while census.phase != 'complete':
            if time.perf_counter() >= deadline: raise TimeoutError('Offline benchmark deadline')
            census.advance(deadline, lambda: None)
    elapsed = time.perf_counter()-started
    diagnostic = census.diagnostic()
    return dict(seconds=elapsed, mib_per_second=reader.size/(1024*1024*elapsed),
        candidates=sorted(census.seen), scan_complete=diagnostic['scan_complete'],
        bytes_scanned=diagnostic['bytes_scanned'], search_seconds=diagnostic['search_seconds'],
        search_full_fallbacks=diagnostic['search_full_fallbacks'])


def benchmark(mib=512):
    if type(mib) is not int or mib < 8 or mib % 8: raise ValueError('MiB must be a positive multiple of 8')
    result = dict(schema_version=2, kind='offline_scanner_cpu', fixture_mib=mib,
        process_reads=0, inputs_sent=0, class_pointer=hex(CLASS), chunk_mib=8,
        excludes=['ReadProcessMemory', 'Windows region enumeration', 'real object inspection'], shapes=[])
    for name, word in (('zero', b'\0'*8), ('sparse_words', b'\0'*6+b'\x01\x00'),
                       ('typed_words', struct.pack('<Q', 0x1911234A000)),
                       ('prefix_collisions', struct.pack('<Q', CLASS | (1 << 56)))):
        raw = bytearray(word*(CHUNK//8))
        struct.pack_into('<Q', raw, CHUNK//2, CLASS)
        chunk = bytes(raw)
        before = _run(chunk, mib//8, aligned=False)
        after = _run(chunk, mib//8, aligned=True)
        if before['candidates'] != after['candidates'] or not before['scan_complete'] or not after['scan_complete']:
            raise AssertionError('Offline coverage changed')
        candidates = len(after.pop('candidates')); before.pop('candidates')
        result['shapes'].append(dict(shape=name, full_pointer=before, aligned_pointer=after,
            identical_candidates=True, candidate_count=candidates, speedup=before['seconds']/after['seconds']))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mib', type=int, default=512)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = benchmark(args.mib)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__': main()
