"""Incomplete heap discovery cannot masquerade as a closed palette or authorize input."""
import struct
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from native_live import native_provider_backend as provider
from native_live import scan_live_dye as scanning
from native_live.collect_dye_validation import collect_validation_session
from test_native_live_session_budget import PassiveBackend


class Clock:
    def __init__(self):self.now=1.
    def __call__(self):return self.now
    def advance(self,seconds):self.now+=seconds


class HeapReader:
    """External process-memory boundary, with literal aligned object headers."""
    def __init__(self,clock,objects,*,cost=.2):
        self.clock=clock;self.cost=cost;self.guard=lambda:None;self.base=0x10000000
        self.memory=bytearray(64);self.objects=objects
        for address in objects:struct.pack_into('<Q',self.memory,address-0x10000,0x200000000)
    def regions(self):
        yield SimpleNamespace(BaseAddress=0x10000,RegionSize=64,State=0x1000,Type=0x20000,Protect=4)
    def u64(self,address):return 0x200000000
    def read(self,address,size):
        self.guard();self.clock.advance(self.cost)
        return bytes(self.memory[address-0x10000:address-0x10000+size])


def eligible(reader,address,cls):
    reader.guard();reader.clock.advance(.06)
    if address not in reader.objects:return None
    return dict(address=hex(address),capture_eligible=reader.objects[address])


class NativeDiscoveryBudgetTests(unittest.TestCase):
    def backend(self,objects,*,cost=.2):
        clock=Clock();reader=HeapReader(clock,objects,cost=cost)
        backend=object.__new__(provider.CurrentBuildBackend)
        backend.reader=reader;backend.scans=0;backend.clock=clock
        backend._bind=lambda check:(check(),0x200000000)[1]
        backend.process_identity=lambda:(7,8,9,'fixture')
        return backend,reader,clock

    def test_early_candidate_survives_slice_until_the_rest_is_checked(self):
        backend,reader,clock=self.backend({0x10000:True})
        with patch.object(scanning,'inspect',side_effect=eligible),patch.object(provider,'inspect',side_effect=eligible):
            self.assertIsNone(backend.discover(20.,lambda:None))
            diagnostic=backend.last_discovery_diagnostic
            self.assertFalse(diagnostic['scan_complete'])
            self.assertEqual(diagnostic['eligible_addresses'],['0x10000'])
            self.assertEqual(backend.discover(20.,lambda:None),0x10000)
        self.assertTrue(backend.last_discovery_diagnostic['uniqueness_verified'])
        self.assertEqual(backend.scans,1)

    def test_later_second_candidate_blocks_selection_across_slices(self):
        backend,reader,clock=self.backend({0x10000:True,0x10038:True})
        with patch.object(scanning,'inspect',side_effect=eligible),patch.object(provider,'inspect',side_effect=eligible):
            self.assertIsNone(backend.discover(20.,lambda:None))
            self.assertIsNone(backend.discover(20.,lambda:None))
            self.assertIsInstance(getattr(backend,'last_discovery_diagnostic',None),dict)
            self.assertFalse(backend.last_discovery_diagnostic['uniqueness_verified'])
            self.assertEqual(backend.last_discovery_diagnostic['eligible_addresses'],['0x10000','0x10038'])

    def test_candidate_that_ends_before_scan_completion_is_not_returned(self):
        backend,reader,clock=self.backend({0x10000:True})
        with patch.object(scanning,'inspect',side_effect=eligible),patch.object(provider,'inspect',side_effect=eligible):
            self.assertIsNone(backend.discover(20.,lambda:None))
            reader.objects[0x10000]=False
            self.assertIsNone(backend.discover(20.,lambda:None))
        self.assertTrue(backend.last_discovery_diagnostic['scan_complete'])
        self.assertEqual(backend.last_discovery_diagnostic['eligible_addresses'],[])

    def test_initially_inactive_candidate_is_rechecked_for_late_activation(self):
        backend,reader,clock=self.backend({0x10000:False,0x10038:True})
        with patch.object(scanning,'inspect',side_effect=eligible),patch.object(provider,'inspect',side_effect=eligible):
            self.assertIsNone(backend.discover(20.,lambda:None))
            reader.objects[0x10000]=True
            self.assertIsNone(backend.discover(20.,lambda:None))
        self.assertTrue(backend.last_discovery_diagnostic['scan_complete'])
        self.assertFalse(backend.last_discovery_diagnostic['uniqueness_verified'])
        self.assertEqual(backend.last_discovery_diagnostic['eligible_addresses'],['0x10000','0x10038'])

    def test_unreadable_heap_cannot_establish_unique_selection(self):
        backend,reader,clock=self.backend({0x10000:True},cost=0.)
        original=reader.regions
        def regions():
            yield from original()
            yield SimpleNamespace(BaseAddress=0x20000,RegionSize=64,State=0x1000,Type=0x20000,Protect=4)
        reader.regions=regions
        original_read=reader.read
        def read(address,size):
            if address==0x20000:raise OSError('Unreadable second heap region')
            return original_read(address,size)
        reader.read=read
        with patch.object(scanning,'inspect',side_effect=eligible):
            self.assertIsNone(backend.discover(20.,lambda:None))
        self.assertEqual(backend.last_discovery_diagnostic['eligible_addresses'],['0x10000'])
        self.assertEqual(backend.last_discovery_diagnostic['read_failures'],1)
        self.assertFalse(backend.last_discovery_diagnostic['uniqueness_verified'])
        self.assertFalse(backend.last_discovery_diagnostic['scan_complete'])

    def test_final_candidate_read_failure_cannot_hide_a_second_aligned_object(self):
        backend,reader,clock=self.backend({0x10000:True,0x10038:True},cost=0.)
        attempts={}
        def inspect_with_failure(reader,address,cls):
            attempts[address]=attempts.get(address,0)+1
            if address==0x10038 and attempts[address]>=2:
                raise OSError('Second typed object became unreadable')
            return eligible(reader,address,cls)
        with patch.object(scanning,'inspect',side_effect=inspect_with_failure):
            selected=backend.discover(20.,lambda:None)
            if not backend.last_discovery_diagnostic['heap_scan_complete']:
                selected=backend.discover(20.,lambda:None)
        self.assertIsNone(selected)
        self.assertFalse(backend.last_discovery_diagnostic['scan_complete'])
        self.assertFalse(backend.last_discovery_diagnostic['uniqueness_verified'])
        self.assertEqual(backend.last_discovery_diagnostic['candidate_read_failures'],1)
        self.assertEqual(backend.last_discovery_diagnostic['unreadable_candidate_addresses'],['0x10038'])

    def test_initial_candidate_read_failure_is_cleared_only_by_successful_final_inspection(self):
        backend,reader,clock=self.backend({0x10000:True,0x10038:False},cost=0.)
        attempts={}
        def inspect_with_failure(reader,address,cls):
            attempts[address]=attempts.get(address,0)+1
            if address==0x10038 and attempts[address]==1:
                raise OSError('Transient second typed object read')
            return eligible(reader,address,cls)
        with patch.object(scanning,'inspect',side_effect=inspect_with_failure):
            self.assertEqual(backend.discover(20.,lambda:None),0x10000)
        self.assertTrue(backend.last_discovery_diagnostic['scan_complete'])
        self.assertEqual(backend.last_discovery_diagnostic.get('candidate_read_failures',0),0)

    def test_cancellation_and_external_timeout_are_not_swallowed_as_read_failures(self):
        for exception in (InterruptedError('Cancelled'),TimeoutError('External deadline')):
            with self.subTest(exception=type(exception).__name__):
                backend,reader,clock=self.backend({0x10000:True})
                reader.read=lambda *args:(_ for _ in ()).throw(exception)
                with self.assertRaises(type(exception)):backend.discover(20.,lambda:None)
                self.assertEqual(backend.last_discovery_diagnostic['read_failures'],0)
                self.assertFalse(backend.last_discovery_diagnostic['scan_complete'])

    def test_class_uninitialized_discards_the_old_incomplete_census(self):
        backend,reader,clock=self.backend({0x10000:True})
        with patch.object(scanning,'inspect',side_effect=eligible):
            self.assertIsNone(backend.discover(20.,lambda:None))
            backend._bind=lambda check:(_ for _ in ()).throw(provider.DyeClassUnavailable('Not initialized'))
            self.assertIsNone(backend.discover(20.,lambda:None))
        self.assertIsNone(backend._discovery_scan)
        self.assertEqual(backend.last_discovery_diagnostic['eligible_addresses'],[])
        self.assertEqual(backend.last_discovery_diagnostic['status'],'class_uninitialized')

    def test_exact_build_uninitialized_class_token_is_verified_absence_without_heap_scan(self):
        for token in (0,provider.UNINITIALIZED_DYE_CLASS_TOKEN):
            with self.subTest(token=hex(token)):
                backend,reader,clock=self.backend({})
                backend.base=reader.base;backend._bind=provider.CurrentBuildBackend._bind.__get__(backend)
                reader.u64=lambda address:token
                self.assertIsNone(backend.discover(20.,lambda:None))
                self.assertTrue(backend.last_discovery_diagnostic.get('initial_absence_verified',False))
                self.assertFalse(backend.last_discovery_diagnostic['scan_complete'])
                self.assertEqual(backend.scans,0)

    def test_fresh_uninitialized_class_can_arm_before_opening_a_finite_round(self):
        backend,reader,clock=self.backend({})
        backend.base=reader.base;backend._bind=provider.CurrentBuildBackend._bind.__get__(backend)
        reader.u64=lambda address:provider.UNINITIALIZED_DYE_CLASS_TOKEN
        backend.observe_window_context=lambda *args,**kwargs:dict(extent_one_to_one=True)
        events=[]
        result=collect_validation_session(backend,wait_seconds=.5,clock=clock,pause=clock.advance,
            event=events.append)
        self.assertTrue(any(row['event']=='armed' for row in events))
        self.assertEqual(result['stop_reason'],'no_active_palette_timeout')
        self.assertEqual(backend.scans,0)
        self.assertEqual(result['inputs_sent'],0)

    def test_unknown_low_class_value_is_rejected_instead_of_verified_absence(self):
        backend,reader,clock=self.backend({})
        backend.base=reader.base;backend._bind=provider.CurrentBuildBackend._bind.__get__(backend)
        reader.u64=lambda address:8
        with self.assertRaisesRegex(ValueError,'build mismatch'):
            backend.discover(20.,lambda:None)

    def test_changing_initial_class_marker_does_not_claim_absence(self):
        backend,reader,clock=self.backend({})
        backend.base=reader.base;backend._bind=provider.CurrentBuildBackend._bind.__get__(backend)
        values=iter((provider.UNINITIALIZED_DYE_CLASS_TOKEN,0x200000000))
        reader.u64=lambda address:next(values)
        self.assertIsNone(backend.discover(20.,lambda:None))
        self.assertFalse(backend.last_discovery_diagnostic['initial_absence_verified'])
        self.assertEqual(backend.last_discovery_diagnostic['status'],'class_initializing')


    def test_process_change_cannot_reuse_the_partial_census(self):
        backend,reader,clock=self.backend({0x10000:True})
        with patch.object(scanning,'inspect',side_effect=eligible):
            self.assertIsNone(backend.discover(20.,lambda:None))
            backend.process_identity=lambda:(7,88,9,'fixture')
            with self.assertRaisesRegex(OSError,'Process/class changed'):
                backend.discover(20.,lambda:None)
        self.assertIsNone(backend._discovery_scan)

    def test_next_census_rechecks_known_candidate_early_but_does_not_skip_new_allocations(self):
        backend,reader,clock=self.backend({0x10000:True})
        with patch.object(scanning,'inspect',side_effect=eligible):
            self.assertIsNone(backend.discover(20.,lambda:None))
            self.assertEqual(backend.discover(20.,lambda:None),0x10000)
            reader.objects[0x10038]=True
            struct.pack_into('<Q',reader.memory,56,0x200000000)
            self.assertIsNone(backend.discover(20.,lambda:None))
            self.assertEqual(backend.last_discovery_diagnostic['eligible_addresses'],['0x10000'])
            self.assertFalse(backend.last_discovery_diagnostic['scan_complete'])
            self.assertIsNone(backend.discover(20.,lambda:None))
        self.assertEqual(backend.scans,2)
        self.assertEqual(backend.last_discovery_diagnostic['eligible_addresses'],['0x10000','0x10038'])
        self.assertFalse(backend.last_discovery_diagnostic['uniqueness_verified'])

    def test_expired_priming_retains_process_window_and_progress_without_input(self):
        clock=Clock();events=[]
        class HeavyBackend:
            def process_identity(self):return [7,8,9,'fixture']
            def observe_window_context(self,*args,**kwargs):
                clock.advance(.5)
                return dict(extent_one_to_one=True,window=dict(client_size_physical=[2560,1369]))
            def discover(self,deadline,check):
                self.last_discovery_diagnostic=dict(scan_complete=False,bytes_scanned=8388608,
                    eligible_addresses=['0x10000'],uniqueness_verified=False)
                clock.advance(30.);check()
        result=collect_validation_session(HeavyBackend(),wait_seconds=30.,clock=clock,event=events.append)
        self.assertEqual(result['stop_reason'],'initial_discovery_timeout')
        self.assertEqual(result['process_identity'],[7,8,9,'fixture'])
        self.assertEqual(result['preflight_window_context']['window']['client_size_physical'],[2560,1369])
        self.assertEqual(result['discovery_progress']['eligible_addresses'],['0x10000'])
        self.assertGreaterEqual(result['phase_seconds']['discovery'],30.)
        self.assertEqual(result['inputs_sent'],0)
        self.assertFalse(result['ready_for_input'])
        self.assertFalse(any(row['event']=='armed' for row in events))

    def test_waiting_expiry_with_pending_uniqueness_is_not_no_active_palette(self):
        clock=Clock()
        class PendingBackend:
            calls=0
            def process_identity(self):return [7,8,9,'fixture']
            def observe_window_context(self,*args,**kwargs):return dict(extent_one_to_one=True)
            def discover(self,deadline,check):
                self.calls+=1
                self.last_discovery_diagnostic=dict(scan_complete=self.calls==1,bytes_scanned=64,
                    eligible_addresses=[] if self.calls==1 else ['0x10000'],uniqueness_verified=False)
                clock.advance(.2);check();return None
        result=collect_validation_session(PendingBackend(),wait_seconds=.5,clock=clock,
            pause=clock.advance)
        self.assertEqual(result['stop_reason'],'discovery_incomplete_timeout')
        self.assertEqual(result['inputs_sent'],0)
        self.assertIn('waiting_deadline_monotonic',result)

    def test_warmup_must_complete_before_armed_and_unknown_age_keeps_90_seconds(self):
        clock=Clock();events=[]
        class WarmingBackend(PassiveBackend):
            def discover(self,deadline,check):
                self.discovers+=1;clock.advance(1.)
                self.last_discovery_diagnostic=dict(status='scanning' if self.discovers<3 else 'complete',
                    scan_complete=self.discovers>=3,eligible_addresses=['0x7b'],
                    first_eligible_seen_monotonic=1.,uniqueness_verified=self.discovers>=3)
                return 123 if self.discovers>=3 else None
        result=collect_validation_session(WarmingBackend(True),session_seconds=110.,dwell_seconds=.1,
            clock=clock,pause=clock.advance,event=events.append)
        self.assertEqual(result['stop_reason'],'passive_baseline_collected')
        self.assertEqual(result['session_deadline_monotonic'],91.)
        self.assertTrue(result['existing_active_palette'])
        armed=next(index for index,row in enumerate(events) if row['event']=='armed')
        progress=[row for row in events[:armed] if row['event']=='discovery_progress']
        self.assertEqual([row['discovery']['scan_complete'] for row in progress],[False,False,True])
        self.assertEqual(result['inputs_sent'],0)

    def test_validation_timeout_records_the_phase_and_process_duration(self):
        clock=Clock()
        class SlowIdentity:
            def process_identity(self):clock.advance(31.);return [7,8,9,'fixture']
        result=collect_validation_session(SlowIdentity(),clock=clock)
        self.assertEqual(result['stop_reason'],'initial_validation_timeout')
        self.assertEqual(result['initial_validation_phase'],'process_identity')
        self.assertEqual(result['phase_seconds']['process_identity'],31.)
        self.assertEqual(result['process_identity'],[7,8,9,'fixture'])
        self.assertEqual(result['inputs_sent'],0)

    def test_window_timeout_keeps_partial_measured_context_and_duration(self):
        clock=Clock()
        class SlowWindow:
            def process_identity(self):return [7,8,9,'fixture']
            def observe_window_context(self,deadline,check,**kwargs):
                self.last_window_diagnostic=dict(unity_screen=dict(size=[2560,1369]),
                    window=dict(client_size_physical=[2560,1369]),ready_for_input=False)
                clock.advance(31.);check()
        result=collect_validation_session(SlowWindow(),clock=clock)
        self.assertEqual(result['stop_reason'],'initial_validation_timeout')
        self.assertEqual(result['initial_validation_phase'],'window_context')
        self.assertEqual(result['phase_seconds']['window_context'],31.)
        self.assertEqual(result['preflight_window_context']['unity_screen']['size'],[2560,1369])
        self.assertEqual(result['inputs_sent'],0)

    def test_already_active_palette_limits_unfinished_warmup_from_first_observation(self):
        clock=Clock();events=[]
        class PendingBackend:
            def process_identity(self):return [7,8,9,'fixture']
            def observe_window_context(self,*args,**kwargs):return dict(extent_one_to_one=True)
            def discover(self,deadline,check):
                self.last_discovery_diagnostic=dict(status='scanning',scan_complete=False,
                    eligible_addresses=['0x10000'],uniqueness_verified=False,first_eligible_seen_monotonic=1.)
                clock.advance(10.);check();return None
        result=collect_validation_session(PendingBackend(),wait_seconds=300.,session_seconds=110.,
            clock=clock,pause=clock.advance,event=events.append)
        self.assertEqual(result['stop_reason'],'initial_discovery_timeout')
        self.assertEqual(result['elapsed_seconds'],90.)
        self.assertFalse(any(row['event']=='armed' for row in events))
        self.assertEqual(result['inputs_sent'],0)

    def test_ambiguous_active_candidates_timeout_is_not_a_closed_palette(self):
        clock=Clock();events=[]
        class AmbiguousBackend:
            def process_identity(self):return [7,8,9,'fixture']
            def observe_window_context(self,*args,**kwargs):return dict(extent_one_to_one=True)
            def discover(self,deadline,check):
                self.last_discovery_diagnostic=dict(scan_complete=True,
                    eligible_addresses=['0x10000','0x10038'],uniqueness_verified=False)
                clock.advance(.2);check();return None
        result=collect_validation_session(AmbiguousBackend(),wait_seconds=.5,clock=clock,
            pause=clock.advance,event=events.append)
        self.assertEqual(result['stop_reason'],'ambiguous_active_palette_timeout')
        self.assertFalse(any(row['event']=='armed' for row in events))
        self.assertEqual(result['inputs_sent'],0)


if __name__=='__main__':unittest.main()
