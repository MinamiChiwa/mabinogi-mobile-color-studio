"""A failed heap read is repaired locally; unknown holes never authorize input."""
import struct
import time
from types import SimpleNamespace

import pytest

from native_live.scan_live_dye import IncrementalDyeScan

BASE = 0x10000
CLASS = 0x19115BA8C80


def region(base=BASE, size=8192, state=0x1000):
    return SimpleNamespace(BaseAddress=base, RegionSize=size, State=state,
                           Type=0x20000, Protect=4)


class Heap:
    def __init__(self, mode):
        self.mode, self.reads = mode, []
        self.data = bytearray(8192)
        # Header at the final aligned word of the first page.
        struct.pack_into('<Q', self.data, 4088, CLASS)

    def regions(self):
        yield region()

    def query_region(self, address):
        if self.mode == 'freed' and address >= BASE + 4096:
            return region(BASE + 4096, 4096, 0x10000)
        if self.mode in ('freed', 'hole'):
            return region(BASE if address < BASE + 4096 else BASE + 4096, 4096)
        return region()

    def read(self, address, size):
        self.reads.append((address, size))
        if len(self.reads) == 1 or (self.mode == 'large' and size > 4096):
            raise OSError(299, 'simulated changing page')
        if self.mode in ('hole', 'freed') and address + size > BASE + 4096:
            raise OSError(299, 'second page unavailable')
        if self.mode == 'short' and len(self.reads) == 2:
            return bytes(size - 1)
        offset = address - BASE
        return bytes(self.data[offset:offset + size])


def run_scan(heap, monkeypatch):
    def inspect(_reader, address, _cls):
        assert address == BASE + 4088
        return {'capture_eligible': True}
    monkeypatch.setattr('native_live.scan_live_dye.inspect', inspect)
    scan = IncrementalDyeScan(heap, CLASS)
    for _ in range(100):
        diagnostic = scan.advance(time.monotonic() + 2, lambda: None)
        if diagnostic['census_finished']:
            return diagnostic
    pytest.fail('scan did not finish')


@pytest.mark.parametrize('mode', ['transient', 'large', 'short', 'freed'])
def test_local_repair_keeps_header_and_proves_unique(mode, monkeypatch):
    heap = Heap(mode)
    diagnostic = run_scan(heap, monkeypatch)
    assert diagnostic['scan_complete'] and diagnostic['uniqueness_verified']
    assert diagnostic['eligible_addresses'] == [hex(BASE + 4088)]
    assert diagnostic['read_failures'] == 0 and diagnostic['read_errors_seen'] >= 1
    assert len(heap.reads) < 15
    if mode == 'freed':
        assert diagnostic['changed_ranges_excluded'] == 1


def test_readable_hole_remains_blocking(monkeypatch):
    diagnostic = run_scan(Heap('hole'), monkeypatch)
    assert diagnostic['census_finished']
    assert diagnostic['status'] == 'coverage_incomplete'
    assert not diagnostic['uniqueness_verified']
    assert diagnostic['read_failures'] == 1
    assert diagnostic['unresolved_read_ranges'][0]['address'] == hex(BASE + 4096)


def test_repair_checks_cancel_before_read(monkeypatch):
    heap = Heap('transient')
    scan = IncrementalDyeScan(heap, CLASS)
    scan._failed_read(BASE, 8192, 'temporary', -1)
    def cancel():
        raise InterruptedError('cancelled')
    with pytest.raises(InterruptedError):
        scan.advance(time.monotonic() + 2, cancel)
    assert heap.reads == []
