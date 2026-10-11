"""Fast heap search preserves the same complete, read-only discovery proof."""
import ctypes
import random
import struct
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from native_live import runtime_read
from native_live import native_provider_backend as provider
from native_live import scan_live_dye as scanning
from test_native_discovery_budget import Clock
from test_native_region_reader import DyeMemory, backend


class SearchBytes(bytes):
    needles = None

    def find(self, needle, start=0, end=None):
        self.needles.append(needle)
        return super().find(needle, start) if end is None else super().find(needle, start, end)


class PatternHeap:
    cls = 0x19115BA8C80

    def __init__(self, size=256):
        self.clock = Clock()
        self.base = 0x10000
        self.memory = bytearray(size)
        self.needles = []
        self.inspections = []

    def put(self, offset, value=None):
        struct.pack_into('<Q', self.memory, offset, self.cls if value is None else value)

    def regions(self):
        yield SimpleNamespace(BaseAddress=self.base, RegionSize=len(self.memory), State=0x1000, Type=0x20000, Protect=4)

    def read(self, address, size):
        self.clock.advance(.01)
        result = SearchBytes(self.memory[address-self.base:address-self.base+size])
        result.needles = self.needles
        return result

    def inspect(self, reader, address, cls):
        self.inspections.append(address)
        return dict(address=hex(address), capture_eligible=True)


class NativeFastDiscoveryTests(unittest.TestCase):
    def test_zero_suffix_search_uses_prefix_but_rejects_every_nonexact_pointer(self):
        memory = PatternHeap()
        pattern = struct.pack('<Q', memory.cls)
        memory.put(0)
        memory.put(32, memory.cls | (1 << 56))
        memory.put(63)
        # A prefix at the final bytes is neither a complete pointer nor an object.
        memory.memory[-6:] = pattern[:6]
        scan = scanning.IncrementalDyeScan(memory, memory.cls, clock=memory.clock)
        with patch.object(scanning, 'inspect', side_effect=memory.inspect):
            diagnostic = scan.advance(20., lambda: None)
        self.assertTrue(diagnostic['uniqueness_verified'], diagnostic)
        self.assertEqual(diagnostic['eligible_addresses'], [hex(memory.base)])
        self.assertEqual(memory.inspections, [memory.base, memory.base])
        self.assertTrue(memory.needles)
        self.assertTrue(all(needle == pattern[:6] for needle in memory.needles))
        self.assertEqual(diagnostic['search_pattern_bytes'], 6)
        self.assertGreaterEqual(diagnostic['read_seconds'], .01)
        self.assertGreater(diagnostic['throughput_mib_per_second'], 0.)

    def test_overlap_keeps_both_aligned_objects_at_the_chunk_boundary(self):
        chunk = 8 * 1024 * 1024
        memory = PatternHeap(chunk + 32)
        memory.put(chunk-8); memory.put(chunk)
        scan = scanning.IncrementalDyeScan(memory, memory.cls, clock=memory.clock)
        with patch.object(scanning, 'inspect', side_effect=memory.inspect):
            first = scan.advance(20., lambda: None, max_bytes=chunk)
            self.assertFalse(first['scan_complete'])
            diagnostic = scan.advance(20., lambda: None)
        expected = [hex(memory.base+chunk-8), hex(memory.base+chunk)]
        self.assertEqual(diagnostic['eligible_addresses'], expected)
        self.assertTrue(diagnostic['scan_complete'])
        self.assertFalse(diagnostic['uniqueness_verified'])
        self.assertEqual(diagnostic['candidate_count'], 2)

    def test_dense_prefix_collisions_use_full_search_without_discarding_a_later_object(self):
        memory = PatternHeap(8192)
        for offset in range(0, 4096, 8): memory.put(offset, memory.cls | (1 << 56))
        memory.put(4096)
        scan = scanning.IncrementalDyeScan(memory, memory.cls, clock=memory.clock)
        with patch.object(scanning, 'inspect', side_effect=memory.inspect):
            diagnostic = scan.advance(20., lambda: None)
        self.assertTrue(diagnostic['uniqueness_verified'], diagnostic)
        self.assertEqual(diagnostic['eligible_addresses'], [hex(memory.base+4096)])
        self.assertEqual(diagnostic['candidate_count'], 1)
        self.assertEqual(diagnostic['search_full_fallbacks'], 1)
        self.assertIn(struct.pack('<Q', memory.cls), memory.needles)
        self.assertLess(len(memory.needles), 64)

    def test_low_zero_density_block_uses_exact_search_and_keeps_identical_census(self):
        memory = PatternHeap(8192)
        memory.memory[:] = struct.pack('<Q', 0x1911234A000)*1024
        memory.put(4096)
        scan = scanning.IncrementalDyeScan(memory, memory.cls, clock=memory.clock)
        with patch.object(scanning, 'inspect', side_effect=memory.inspect):
            diagnostic = scan.advance(20., lambda: None)
        self.assertTrue(diagnostic['uniqueness_verified'], diagnostic)
        self.assertEqual(diagnostic['eligible_addresses'], [hex(memory.base+4096)])
        self.assertTrue(all(needle == struct.pack('<Q', memory.cls) for needle in memory.needles))
        self.assertEqual(diagnostic['exact_search_blocks'], 1)

    def test_both_search_strategies_match_reference_for_varied_pointer_layouts(self):
        for cls in (0x100000000, 0x19115BA8C80, 0x7FFFFFFFEFE8):
            for zero_heavy in (False, True):
                with self.subTest(cls=hex(cls), zero_heavy=zero_heavy):
                    memory = PatternHeap(8192); memory.cls = cls
                    if not zero_heavy: memory.memory[:] = random.Random(31).randbytes(8192)
                    for offset in (0, 9, 80, 128, 4072, 4081, 6144, 8184): memory.put(offset)
                    memory.put(512, cls | (1 << 56))
                    expected = [memory.base+offset for offset in range(0, len(memory.memory)-7, 8)
                        if struct.unpack_from('<Q', memory.memory, offset)[0] == cls]
                    scan = scanning.IncrementalDyeScan(memory, cls, clock=memory.clock)
                    with patch.object(scanning, 'inspect', side_effect=memory.inspect):
                        diagnostic = scan.advance(20., lambda: None)
                    self.assertEqual(sorted(scan.seen), expected)
                    self.assertTrue(diagnostic['scan_complete'])
                    self.assertEqual(diagnostic['candidate_count'], len(expected))

    def test_cancelled_prefix_candidate_inspection_keeps_cursor_for_resume(self):
        memory = PatternHeap(); memory.put(0); memory.put(16)
        scan = scanning.IncrementalDyeScan(memory, memory.cls, clock=memory.clock)
        attempts = [0]
        def interrupted(reader, address, cls):
            attempts[0] += 1
            if attempts[0] == 1: raise InterruptedError('F9')
            return memory.inspect(reader, address, cls)
        with patch.object(scanning, 'inspect', side_effect=interrupted):
            with self.assertRaises(InterruptedError): scan.advance(20., lambda: None)
            self.assertEqual(scan.find_position, 0)
            self.assertEqual(scan.seen, set())
            diagnostic = scan.advance(20., lambda: None)
        self.assertTrue(diagnostic['scan_complete'])
        self.assertEqual(diagnostic['candidate_count'], 2)
        self.assertFalse(diagnostic['uniqueness_verified'])

    def test_identity_change_after_census_invalidates_complete_discovery_proof(self):
        memory = PatternHeap(); memory.put(0)
        subject = object.__new__(provider.CurrentBuildBackend)
        subject.reader = memory; subject.clock = memory.clock; subject.scans = 0
        subject._bind = lambda check: memory.cls
        identities = iter(((7, 8, 9, 'fixture'), (7, 88, 9, 'fixture')))
        subject.process_identity = lambda: next(identities)
        with patch.object(scanning, 'inspect', side_effect=memory.inspect):
            with self.assertRaisesRegex(OSError, 'Process changed'): subject.discover(20., lambda: None)
        self.assertIsNone(subject._discovery_scan)
        self.assertFalse(subject.last_discovery_diagnostic['scan_complete'])
        self.assertFalse(subject.last_discovery_diagnostic['uniqueness_verified'])
        self.assertEqual(subject.last_discovery_diagnostic['status'], 'identity_changed')

    def test_process_ending_after_census_invalidates_complete_discovery_proof(self):
        memory = PatternHeap(); memory.put(0)
        subject = object.__new__(provider.CurrentBuildBackend)
        subject.reader = memory; subject.clock = memory.clock; subject.scans = 0
        subject._bind = lambda check: memory.cls
        calls = [0]
        def identity():
            calls[0] += 1
            if calls[0] > 1: raise OSError('Process ended')
            return (7, 8, 9, 'fixture')
        subject.process_identity = identity
        with patch.object(scanning, 'inspect', side_effect=memory.inspect):
            with self.assertRaisesRegex(OSError, 'Process ended'): subject.discover(20., lambda: None)
        self.assertIsNone(subject._discovery_scan)
        self.assertFalse(subject.last_discovery_diagnostic['uniqueness_verified'])

    def test_class_change_before_next_slice_clears_old_candidates_and_scan(self):
        memory = PatternHeap(); memory.put(0)
        subject = object.__new__(provider.CurrentBuildBackend)
        subject.reader = memory; subject.clock = memory.clock; subject.scans = 0
        subject._bind = lambda check: memory.cls
        subject.process_identity = lambda: (7, 8, 9, 'fixture')
        with patch.object(scanning, 'inspect', side_effect=memory.inspect):
            self.assertEqual(subject.discover(20., lambda: None), memory.base)
            memory.cls += 8
            with self.assertRaisesRegex(OSError, 'Process/class changed'): subject.discover(20., lambda: None)
        self.assertIsNone(subject._discovery_scan)
        self.assertFalse(subject.last_discovery_diagnostic['scan_complete'])
        self.assertFalse(subject.last_discovery_diagnostic['uniqueness_verified'])
        self.assertEqual(subject.last_discovery_diagnostic['eligible_addresses'], [])

    def test_bulk_reads_reuse_storage_but_return_independent_exact_length_bytes(self):
        reader = object.__new__(runtime_read.Reader); reader.h = 17
        destinations = []; payloads = [b'A'*65536, b'B'*65536, b'C'*17]
        def rpm(handle, address, destination, size, got):
            payload = payloads.pop(0)
            destinations.append(ctypes.addressof(destination))
            ctypes.memmove(destination, payload, len(payload))
            ctypes.cast(got, ctypes.POINTER(ctypes.c_size_t)).contents.value = len(payload)
            return True
        with patch.object(runtime_read.K, 'ReadProcessMemory', side_effect=rpm):
            first = reader.read(0x10000, 65536)
            second = reader.read(0x20000, 65536)
            short = reader.read(0x30000, 65536)
        self.assertEqual(destinations[0], destinations[1])
        self.assertEqual(destinations[1], destinations[2])
        self.assertEqual(first, b'A'*65536)
        self.assertEqual(second, b'B'*65536)
        self.assertEqual(short, b'C'*17)

    def test_bulk_read_failure_does_not_return_previous_buffer_contents(self):
        reader = object.__new__(runtime_read.Reader); reader.h = 17
        def rpm(handle, address, destination, size, got):
            ctypes.memmove(destination, b'A'*size, size)
            ctypes.cast(got, ctypes.POINTER(ctypes.c_size_t)).contents.value = size
            return True
        with patch.object(runtime_read.K, 'ReadProcessMemory', side_effect=rpm):
            first = reader.read(0x10000, 65536)
        with patch.object(runtime_read.K, 'ReadProcessMemory', return_value=False):
            with self.assertRaises(OSError): reader.read(0x20000, 65536)
        self.assertEqual(first, b'A'*65536)

    def test_inactive_probe_reports_observed_structure_without_a_session_token(self):
        memory = DyeMemory(3)
        memory.put(memory.instance+32, 'Q', 0)
        result = backend(memory, '.').probe(memory.instance, 20., lambda: None)
        self.assertFalse(result['active'])
        self.assertIsNone(result['session_token'])
        diagnostic = result['active_diagnostic']
        self.assertEqual(diagnostic['instance_status'], 'typed_inactive')
        self.assertEqual(diagnostic['active_result'], '0x0')
        self.assertEqual(diagnostic['region_count'], 3)
        self.assertEqual(diagnostic['controller_state'], 2)

    def test_active_probe_keeps_complete_token_and_adds_observed_structure(self):
        memory = DyeMemory(2)
        result = backend(memory, '.').probe(memory.instance, 20., lambda: None)
        self.assertTrue(result['active'])
        self.assertEqual(len(result['session_token']), 7)
        self.assertEqual(result['active_diagnostic']['instance_status'], 'typed_active')
        self.assertTrue(result['active_diagnostic']['capture_eligible'])


class NativeRegionCoverageTests(unittest.TestCase):
    """Win64 API data is supplied as bytes; no test opens a process."""
    def fake_system_info(self, minimum=0x10000, maximum=0x13FFF):
        def populate(pointer):
            # Win64 SYSTEM_INFO: first union+page DWORDs, then three ULONG_PTRs.
            payload = struct.pack('<IIQQQIIIHH', 9, 4096, minimum, maximum, 1, 1, 8664, 65536, 0, 0)
            ctypes.memmove(pointer, payload, 48)
        return populate

    def query_rows(self, rows, calls):
        def query(handle, address, pointer, size):
            calls.append(address)
            row = rows[address]
            if row is None:
                ctypes.set_last_error(299)
                return 0
            base, length, returned = row
            region = ctypes.cast(pointer, ctypes.POINTER(runtime_read.MBI)).contents
            region.BaseAddress = base; region.RegionSize = length
            region.State = 0x1000; region.Type = 0x20000; region.Protect = 4
            return returned
        return query

    def reader(self):
        reader = object.__new__(runtime_read.Reader); reader.h = 17
        return reader

    def test_win64_system_info_layout_matches_native_pointer_abi(self):
        info = runtime_read.SYSTEM_INFO
        self.assertEqual(ctypes.sizeof(info), 48)
        self.assertEqual(info.lpMinimumApplicationAddress.offset, 8)
        self.assertEqual(info.lpMaximumApplicationAddress.offset, 16)
        self.assertEqual(info.dwActiveProcessorMask.offset, 24)
        self.assertEqual(info.dwNumberOfProcessors.offset, 32)
        self.assertEqual(info.wProcessorRevision.offset, 46)

    def test_address_range_ends_normally_at_inclusive_application_maximum(self):
        calls = []; rows = {0x10000: (0x10000, 0x2000, 48), 0x12000: (0x12000, 0x2000, 48)}
        with patch.object(runtime_read.K, 'GetNativeSystemInfo', side_effect=self.fake_system_info()), \
             patch.object(runtime_read.K, 'VirtualQueryEx', side_effect=self.query_rows(rows, calls)):
            result = list(self.reader().regions())
        self.assertEqual(calls, [0x10000, 0x12000])
        self.assertEqual([(row.BaseAddress, row.RegionSize) for row in result], [(0x10000, 0x2000), (0x12000, 0x2000)])

    def test_query_failure_inside_application_range_is_not_normal_completion(self):
        calls = []; rows = {0x10000: (0x10000, 0x2000, 48), 0x12000: None}
        with patch.object(runtime_read.K, 'GetNativeSystemInfo', side_effect=self.fake_system_info()), \
             patch.object(runtime_read.K, 'VirtualQueryEx', side_effect=self.query_rows(rows, calls)):
            iterator = self.reader().regions(); next(iterator)
            with self.assertRaisesRegex(OSError, 'VirtualQueryEx'): next(iterator)
        self.assertEqual(calls, [0x10000, 0x12000])

    def test_invalid_region_sizes_gaps_and_short_api_results_fail_closed(self):
        for base, length, returned in ((0x10000, 0, 48), (0xF000, 0x1000, 48),
                                       (0x11000, 0x1000, 48), (0x10000, 0x8000, 48),
                                       (0x10000, 0x1000, 16)):
            with self.subTest(base=hex(base), length=length, returned=returned):
                calls = []; rows = {0x10000: (base, length, returned)}
                with patch.object(runtime_read.K, 'GetNativeSystemInfo', side_effect=self.fake_system_info()), \
                     patch.object(runtime_read.K, 'VirtualQueryEx', side_effect=self.query_rows(rows, calls)):
                    with self.assertRaises(OSError): next(self.reader().regions())

    def test_invalid_system_bounds_fail_before_any_region_is_accepted(self):
        for minimum, maximum in ((0, 0), (0x20000, 0x10000)):
            with self.subTest(minimum=minimum, maximum=maximum):
                with patch.object(runtime_read.K, 'GetNativeSystemInfo', side_effect=self.fake_system_info(minimum, maximum)), \
                     patch.object(runtime_read.K, 'VirtualQueryEx') as query:
                    with self.assertRaises(OSError): next(self.reader().regions())
                query.assert_not_called()

    def test_failed_region_enumeration_stays_incomplete_after_generator_is_exhausted(self):
        memory = PatternHeap(256); memory.put(0); memory.h = 17
        memory.regions = runtime_read.Reader.regions.__get__(memory)
        calls = []; rows = {0x10000: (0x10000, 128, 48), 0x10080: None}
        with patch.object(runtime_read.K, 'GetNativeSystemInfo', side_effect=self.fake_system_info(0x10000, 0x100FF)), \
             patch.object(runtime_read.K, 'VirtualQueryEx', side_effect=self.query_rows(rows, calls)), \
             patch.object(scanning, 'inspect', side_effect=memory.inspect):
            scan = scanning.IncrementalDyeScan(memory, memory.cls, clock=memory.clock)
            with self.assertRaises(OSError): scan.advance(20., lambda: None)
            diagnostic = scan.advance(20., lambda: None)
        self.assertFalse(diagnostic['scan_complete'])
        self.assertFalse(diagnostic['uniqueness_verified'])
        self.assertEqual(diagnostic['read_failures'], 1)
        self.assertIn('VirtualQueryEx', diagnostic['last_read_error'])

    def test_guard_interruption_after_query_failure_cannot_discard_coverage_error(self):
        memory = PatternHeap(256); memory.put(0)
        failed = [False]
        def regions():
            yield SimpleNamespace(BaseAddress=memory.base, RegionSize=128,
                State=0x1000, Type=0x20000, Protect=4)
            failed[0] = True
            raise OSError('VirtualQueryEx inaccessible region')
        def check():
            if failed[0]: raise InterruptedError('F9')
        memory.regions = regions
        scan = scanning.IncrementalDyeScan(memory, memory.cls, clock=memory.clock)
        with patch.object(scanning, 'inspect', side_effect=memory.inspect):
            with self.assertRaises(InterruptedError): scan.advance(20., check)
            failed[0] = False
            diagnostic = scan.advance(20., check)
        self.assertFalse(diagnostic['scan_complete'])
        self.assertFalse(diagnostic['uniqueness_verified'])
        self.assertEqual(diagnostic['read_failures'], 1)


if __name__ == '__main__': unittest.main()
