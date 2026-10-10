"""TDD contract for binding discovery output to stable observations."""
import importlib,importlib.util,struct,unittest
from test_native_runtime_adapter import FakeReader


class NativeRuntimeBridgeTests(unittest.TestCase):
 def setUp(self):
  self.assertIsNotNone(importlib.util.find_spec('native_runtime_bridge'))
  self.m=importlib.import_module('native_runtime_bridge')
  from native_runtime_adapter import RuntimeLayout
  self.layout=RuntimeLayout(
   motion_fields=dict(settings=8,position_animator=16,rotation_animator=24,current_position=32,current_scale=40,current_rotation=44),
   settings_fields=dict(minimum_scale=0,maximum_scale=4,move_threshold=8,move_tolerance=12,scroll_zoom_ratio=16),
   animator_fields=dict(is_done=0x29,stop_requested=0x2a,animation=0x70),
   position_animation_fields=dict(duration=0x28,last=0x18,target=0x20),
   rotation_animation_fields=dict(duration=0x20,last=0x18,target=0x1c))
  self.reader=FakeReader();self.motion=0x6000;settings=0x7000;pa=0x8000;ra=0x9000;pan=0xa000;ran=0xb000
  self.reader.put(self.motion+8,struct.pack('<Q',settings));self.reader.put(self.motion+16,struct.pack('<Q',pa));self.reader.put(self.motion+24,struct.pack('<Q',ra))
  self.reader.put(self.motion+32,struct.pack('<2f',0,0));self.reader.put(self.motion+40,struct.pack('<f',1));self.reader.put(self.motion+44,struct.pack('<f',0))
  self.reader.put(settings,struct.pack('<5f',.5,3,5,.1,.01))
  for animator,animation,vector in ((pa,pan,True),(ra,ran,False)):
   self.reader.put(animator+0x29,b'\x01');self.reader.put(animator+0x2a,b'\x00');self.reader.put(animator+0x70,struct.pack('<Q',animation))
   self.reader.put(animation+(0x28 if vector else 0x20),struct.pack('<f',0))
   self.reader.put(animation+0x18,struct.pack('<2f' if vector else '<f',*( (0,0) if vector else (0,))))
   self.reader.put(animation+(0x20 if vector else 0x1c),struct.pack('<2f' if vector else '<f',*( (0,0) if vector else (0,))))
  self.instance=dict(address=0x1000,class_name='MM.Client.Presentation.UI.Instances.StageScene.Dyeing.DyeingPaletteInstanceImpl',ui_slot=0x2000,data=0x3000,result=0x4000)
  self.candidate=dict(address=0x5000,class_name='MM.Client.Presentation.UI.Controls.Dyeing.DyeingPaletteControl',ui_slot=0x2000,motion_control=self.motion,gesture_recognizer=0x6100,root_object=0x2000)
  self.context=dict(build_sha256='a'*64,pid=123,process_creation_token=9,capture_id='c',session_token='s',pixel_sha256=('b'*64,'c'*64,'d'*64),
   active=True,
   geometry=dict(board=[757.,428.,1287.,958.],local_size=[624.,624.],camera='null',source='runtime_recttransform'),
   scroll=dict(project_delta=1.,game_delta=1.,sign_verified=True,observed_events=1),monotonic_time=1.)

 def test_reads_unique_control_and_returns_validated_observation(self):
  result=self.m.read_bound_observation(self.reader,self.instance,[self.candidate],self.context,self.layout)
  self.assertEqual(result['control_address'],0x5000);self.assertEqual(result['motion_address'],self.motion)
  self.assertEqual(result['observation']['pose']['scale'],1.)
  self.assertFalse(result['observation']['execution_verified'])

 def test_stable_pair_requires_same_control_chain_and_later_context(self):
  second=dict(self.context,monotonic_time=1.2)
  result=self.m.read_bound_stable_pair(self.reader,self.instance,[self.candidate],self.context,second,self.layout)
  self.assertTrue(result['stable']);self.assertEqual(result['session_token'],'s')
  with self.assertRaises(ValueError):self.m.read_bound_stable_pair(self.reader,self.instance,[self.candidate],self.context,dict(second,session_token='x'),self.layout)

 def test_ambiguous_control_or_unsettled_animator_fails_before_return(self):
  with self.assertRaises(ValueError):self.m.read_bound_observation(self.reader,self.instance,[self.candidate,dict(self.candidate,address=0x5100)],self.context,self.layout)
  self.reader.put(0x8000+0x29,b'\x00')
  with self.assertRaises(ValueError):self.m.read_bound_observation(self.reader,self.instance,[self.candidate],self.context,self.layout)

 def test_cancel_is_checked_between_discovery_and_read(self):
  calls=[]
  def check():
   calls.append(True)
   if len(calls)>2:raise InterruptedError('F9')
  with self.assertRaises(InterruptedError):self.m.read_bound_observation(self.reader,self.instance,[self.candidate],self.context,self.layout,check=check)
  self.assertGreater(len(calls),1)

 def test_pair_timestamps_come_from_read_clock_not_supplied_context(self):
  ticks=iter([10.,10.2])
  first=dict(self.context,monotonic_time=1000.)
  second=dict(self.context,monotonic_time=1001.)
  result=self.m.read_bound_stable_pair(self.reader,self.instance,[self.candidate],first,second,self.layout,
        clock=lambda:next(ticks),pause=lambda:None)
  self.assertEqual(result['observation']['observation_times'],[10.,10.2])

if __name__=='__main__':unittest.main()
