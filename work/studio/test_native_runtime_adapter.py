"""TDD contract for explicit-address, read-only runtime observation adapter."""
import importlib, importlib.util, struct, unittest


class FakeReader:
    def __init__(self): self.mem={}
    def put(self,address,data): self.mem[address]=bytes(data)
    def read(self,address,size):
        raw=bytearray()
        for i in range(size):
            value=0
            for base,data in self.mem.items():
                if base<=address+i<base+len(data): value=data[address+i-base];break
            raw.append(value)
        return bytes(raw)
    def u64(self,address): return struct.unpack('<Q',self.read(address,8))[0]
    def class_name(self,address): return 'Fake.Runtime.Type'


class NativeRuntimeAdapterTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('native_runtime_adapter'))
        self.m=importlib.import_module('native_runtime_adapter')
        self.r=FakeReader()
        # Addresses and offsets are explicit test layout, never production constants.
        self.layout=self.m.RuntimeLayout(
            motion_fields=dict(settings=8,position_animator=16,rotation_animator=24,current_position=32,current_scale=40,current_rotation=44),
            settings_fields=dict(minimum_scale=0,maximum_scale=4,move_threshold=8,move_tolerance=12,scroll_zoom_ratio=16),
            animator_fields=dict(is_done=0x29,stop_requested=0x2a,animation=0x70),
            position_animation_fields=dict(duration=0x28,last=0x18,target=0x20),
            rotation_animation_fields=dict(duration=0x20,last=0x18,target=0x1c))
        self.base=0x1000;self.settings=0x2000;self.pa=0x3000;self.ra=0x4000;self.panim=0x5000;self.ranim=0x6000
        self.r.put(self.base+8,struct.pack('<Q',self.settings));self.r.put(self.base+16,struct.pack('<Q',self.pa));self.r.put(self.base+24,struct.pack('<Q',self.ra))
        self.r.put(self.base+32,struct.pack('<2f',0.,0.));self.r.put(self.base+40,struct.pack('<f',1.));self.r.put(self.base+44,struct.pack('<f',0.))
        self.r.put(self.settings,struct.pack('<5f',.5,3.,5.,.1,.01));self.r.put(self.pa+0x29,b'\x01');self.r.put(self.pa+0x2a,b'\x00');self.r.put(self.pa+0x70,struct.pack('<Q',self.panim))
        self.r.put(self.ra+0x29,b'\x01');self.r.put(self.ra+0x2a,b'\x00');self.r.put(self.ra+0x70,struct.pack('<Q',self.ranim))
        self.r.put(self.panim+0x28,struct.pack('<f',0.));self.r.put(self.panim+0x18,struct.pack('<2f',0.,0.));self.r.put(self.panim+0x20,struct.pack('<2f',0.,0.))
        self.r.put(self.ranim+0x20,struct.pack('<f',0.));self.r.put(self.ranim+0x18,struct.pack('<f',0.));self.r.put(self.ranim+0x1c,struct.pack('<f',0.))
        self.context=dict(build_sha256='a'*64,pid=123,process_creation_token=9,capture_id='c',session_token='s',
            active=True,
            pixel_sha256=('b'*64,'c'*64,'d'*64),geometry=dict(board=[757.,428.,1287.,958.],local_size=[624.,624.],camera='null',source='runtime_recttransform'),
            scroll=dict(project_delta=1.,game_delta=1.,sign_verified=True,observed_events=1),monotonic_time=1.,motion_address=self.base)

    def test_reads_pose_settings_animators_and_validates_record(self):
        record=self.m.read_runtime_observation(self.r,self.context,self.layout)
        self.assertEqual(record['pose'],dict(position=[0.,0.],scale=1.,rotation_degrees=0.))
        self.assertTrue(record['animator']['position']['is_done'])
        self.assertEqual(record['settings']['maximum_scale'],3.)
        self.assertFalse(record['execution_verified'])

    def test_unresolved_animator_and_pointer_failure_close(self):
        self.r.put(self.pa+0x29,b'\x00')
        with self.assertRaises(ValueError):self.m.read_runtime_observation(self.r,self.context,self.layout)
        self.r.put(self.pa+0x29,b'\x01');self.r.put(self.base+8,struct.pack('<Q',0))
        with self.assertRaises(ValueError):self.m.read_runtime_observation(self.r,self.context,self.layout)

    def test_no_geometry_or_missing_context_is_accepted(self):
        with self.assertRaises(ValueError):self.m.read_runtime_observation(self.r,dict(self.context,geometry={}),self.layout)
        with self.assertRaises(ValueError):self.m.read_runtime_observation(self.r,dict(self.context,session_token=''),self.layout)

    def test_cancel_check_is_called_between_reads(self):
        calls=[]
        def check():
            calls.append(True)
            if len(calls)>5: raise InterruptedError('F9')
        with self.assertRaises(InterruptedError):self.m.read_runtime_observation(self.r,self.context,self.layout,check=check)
        self.assertGreater(len(calls),1)

    def test_missing_animator_elapsed_is_unknown_not_replaced_with_duration(self):
        self.r.put(self.panim+0x28,struct.pack('<f',2.))
        record=self.m.read_runtime_observation(self.r,self.context,self.layout)
        self.assertIsNone(record['animator']['position']['elapsed'])
        self.assertFalse(record['animator']['position']['elapsed_observed'])

    def test_inactive_context_is_not_overwritten(self):
        with self.assertRaises(ValueError):
            self.m.read_runtime_observation(self.r,dict(self.context,active=False),self.layout)


if __name__=='__main__':unittest.main()
