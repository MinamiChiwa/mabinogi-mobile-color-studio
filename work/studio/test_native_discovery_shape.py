"""Literal object headers distinguish class-pattern noise from unreadable live candidates."""
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from native_live import native_provider_backend as provider
from native_live.collect_dye_validation import collect_validation_session
from native_live.scan_live_dye import IncrementalDyeScan,inspect
from test_native_discovery_budget import Clock
from test_native_region_reader import DyeMemory


class ShapeMemory(DyeMemory):
    def __init__(self,count=2):
        super().__init__(count);self.clock=Clock();self.failed_address=None
    def regions(self):
        yield SimpleNamespace(BaseAddress=self.base,RegionSize=self.next,State=0x1000,Type=0x20000,Protect=4)
    def read(self,address,size):
        if address<self.base or address==self.failed_address:
            raise OSError(299,f'ReadProcessMemory {address:x}')
        return super().read(address,size)
    def class_name(self,address):
        if address in {row[0] for row in self.classes.values()}:return super().class_name(address)
        # Mirror the real reader's first metadata dereference. Null class ->
        # RPM 10; the other recorded low class -> RPM 6ef9.
        self.u64(address+16)
        raise ValueError('Unrecognized class metadata')
    def noise(self,class_value):
        address=self.allocate(128);data=self.allocate(128)
        self.put(address,'Q',self.u64(self.instance));self.put(address+24,'Q',data)
        self.put(data,'Q',class_value)
        return address


class NativeDiscoveryShapeTests(unittest.TestCase):
    def test_recorded_null_and_small_class_noise_does_not_block_unique_real_two_or_three_region_instance(self):
        for count in (2,3):
            with self.subTest(count=count):
                memory=ShapeMemory(count);noise=[memory.noise(0),memory.noise(0x6ee9)]
                scan=IncrementalDyeScan(memory,memory.u64(memory.instance),clock=memory.clock)
                diagnostic=scan.advance(20.,lambda:None)
                self.assertTrue(diagnostic['scan_complete'],diagnostic)
                self.assertTrue(diagnostic['uniqueness_verified'],diagnostic)
                self.assertEqual(diagnostic['eligible_addresses'],[hex(memory.instance)])
                self.assertEqual(diagnostic['candidate_read_failures'],0)
                self.assertGreaterEqual(diagnostic.get('rejected_candidate_count',0),len(noise))

    def test_valid_typed_object_deep_read_failure_still_blocks_uniqueness(self):
        memory=ShapeMemory();memory.failed_address=memory.data+16
        scan=IncrementalDyeScan(memory,memory.u64(memory.instance),clock=memory.clock)
        diagnostic=scan.advance(20.,lambda:None)
        self.assertFalse(diagnostic['scan_complete'])
        self.assertFalse(diagnostic['uniqueness_verified'])
        self.assertIn(hex(memory.instance),diagnostic['unreadable_candidate_addresses'])

    def test_second_real_instance_that_activates_after_initial_inspection_blocks_uniqueness(self):
        for count in (2,3):
            with self.subTest(count=count):
                memory=ShapeMemory(count);second=memory.allocate(128)
                memory.bytes(second,memory.read(memory.instance,128));memory.put(second+32,'Q',0)
                scan=IncrementalDyeScan(memory,memory.u64(memory.instance),clock=memory.clock)
                for _ in range(30):
                    diagnostic=scan.advance(20.,lambda:None,max_candidates=1)
                    if second in scan.seen:break
                self.assertIn(second,scan.seen)
                memory.put(second+32,'Q',memory.result)
                diagnostic=scan.advance(20.,lambda:None)
                self.assertTrue(diagnostic['scan_complete'],diagnostic)
                self.assertFalse(diagnostic['uniqueness_verified'])
                self.assertEqual(diagnostic['eligible_addresses'],[hex(memory.instance),hex(second)])

    def test_inactive_instance_with_null_resources_remains_a_typed_candidate(self):
        memory=ShapeMemory();fields=memory.fields(memory.u64(memory.instance))
        memory.put(memory.instance+fields['<Result>k__BackingField'],'Q',0)
        memory.put(memory.data+32,'Q',0)
        for fragment in memory.fragments:memory.put(fragment+32,'Q',0)
        state=inspect(memory,memory.instance,memory.u64(memory.instance))
        self.assertIsInstance(state,dict)
        self.assertFalse(state['capture_eligible'])
        self.assertEqual(state['region_count'],2)

    def test_invalid_metadata_string_pointer_is_shape_noise_rather_than_unknown_read(self):
        memory=ShapeMemory();address=memory.noise(memory.allocate(256))
        data=memory.u64(address+24);metadata=memory.u64(data)
        memory.put(metadata+16,'Q',0x6ef9)
        scan=IncrementalDyeScan(memory,memory.u64(memory.instance),clock=memory.clock)
        diagnostic=scan.advance(20.,lambda:None)
        self.assertTrue(diagnostic['uniqueness_verified'],diagnostic)
        self.assertEqual(diagnostic['candidate_read_failures'],0)
        self.assertIn(hex(address),diagnostic['rejected_candidates'])

    def test_valid_unaligned_metadata_string_address_is_allowed(self):
        memory=ShapeMemory();cls=memory.u64(memory.instance)
        name=memory.u64(cls+16);raw=memory.read(name,256).split(b'\0',1)[0]
        replacement=memory.allocate(272)+1;memory.bytes(replacement,raw+b'\0')
        memory.put(cls+16,'Q',replacement)
        state=inspect(memory,memory.instance,cls)
        self.assertTrue(state['capture_eligible'])

    def test_missing_required_field_rejects_noise_instead_of_raising_key_error(self):
        memory=ShapeMemory();cls=memory.u64(memory.instance);table=memory.u64(cls+0x80)
        memory.put(table+16,'Q',0)
        scan=IncrementalDyeScan(memory,cls,clock=memory.clock)
        diagnostic=scan.advance(20.,lambda:None)
        self.assertTrue(diagnostic['scan_complete'],diagnostic)
        self.assertFalse(diagnostic['uniqueness_verified'])
        self.assertEqual(diagnostic['candidate_read_failures'],0)

    def test_f9_during_discovery_preserves_partial_baseline_and_never_captures(self):
        clock=Clock();events=[]
        class CancelledBackend:
            def process_identity(self):return [7,8,9,'fixture']
            def observe_window_context(self,*args,**kwargs):return dict(extent_one_to_one=True)
            def discover(self,deadline,check):
                self.last_discovery_diagnostic=dict(status='coverage_incomplete',census_finished=True,
                    scan_complete=False,eligible_addresses=[],candidate_read_failures=1,bytes_scanned=1234)
                raise InterruptedError('F9')
        result=collect_validation_session(CancelledBackend(),clock=clock,event=events.append)
        self.assertEqual(result['stop_reason'],'interrupted')
        self.assertEqual(result['process_identity'],[7,8,9,'fixture'])
        self.assertTrue(result['preflight_window_context']['extent_one_to_one'])
        self.assertEqual(result['discovery_progress']['bytes_scanned'],1234)
        self.assertEqual(result['inputs_sent'],0)
        self.assertFalse(any(row['event']=='discovery_blocked' for row in events))

    def test_service_writes_interrupted_discovery_baseline_without_constructing_input_adapter(self):
        from native_live import service
        from window_target import WindowTarget
        class CancelledBackend:
            closed=False
            def process_identity(self):return [7,8,9,'fixture']
            def observe_window_context(self,*args,**kwargs):return dict(extent_one_to_one=True)
            def discover(self,deadline,check):
                self.last_discovery_diagnostic=dict(status='scanning',scan_complete=False,
                    eligible_addresses=[],candidate_read_failures=0,bytes_scanned=1234)
                raise InterruptedError('F9')
            def close(self):self.closed=True
        backend=CancelledBackend()
        with tempfile.TemporaryDirectory() as folder:
            owner=SimpleNamespace(folder=Path(folder),stop=threading.Event(),event=lambda *args,**kwargs:None)
            with patch.object(service,'_prepare',return_value=(backend,{})), \
                 patch.object(service,'resolve_target',return_value=WindowTarget(20,7,'Game','game.exe')), \
                 patch.object(service.u,'GetAsyncKeyState',return_value=0), \
                 patch.object(service,'ProjectClosedLoopIO') as adapter:
                result=service.run_native_search(owner,[dict(enabled=True,exact=True,colors=['#000000'],tolerance=0.)]*3)
            saved=json.loads((Path(folder)/'native-baseline.json').read_text(encoding='utf-8'))
        self.assertEqual(saved['stop_reason'],'interrupted')
        self.assertEqual(saved['discovery_progress']['bytes_scanned'],1234)
        self.assertEqual(result['actual_input_attempts'],0)
        self.assertTrue(backend.closed);adapter.assert_not_called()

    def test_finished_census_with_real_read_failure_stops_once_and_emits_diagnostic(self):
        memory=ShapeMemory();memory.failed_address=memory.data+16
        backend=object.__new__(provider.CurrentBuildBackend)
        backend.reader=memory;backend.clock=memory.clock;backend.scans=0
        backend.process_identity=lambda:(7,8,9,'fixture')
        backend._bind=lambda check:(check(),memory.u64(memory.instance))[1]
        backend.observe_window_context=lambda *args,**kwargs:dict(extent_one_to_one=True)
        events=[]
        result=collect_validation_session(backend,wait_seconds=.5,clock=memory.clock,
            pause=memory.clock.advance,event=events.append)
        self.assertEqual(result['stop_reason'],'discovery_read_failure')
        self.assertEqual(backend.scans,1)
        self.assertTrue(any(row['event']=='discovery_blocked' for row in events))
        self.assertEqual(result['inputs_sent'],0)
        self.assertFalse(any(row['event']=='armed' for row in events))


if __name__=='__main__':unittest.main()
