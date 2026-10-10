"""Protect whole-route pivot edits, endpoint scoring and bounded retention."""
from test_support import read_local_fixture_text
from test_support import load_local_palette_session
import importlib,importlib.util,json,unittest
from pathlib import Path
from native_input_response import InputGeometry,InputSettings,replay_native_route
from native_palette_scoring import load_session
from input_gestures import wheel_gesture


class NativeInputPivotRefineTests(unittest.TestCase):
 def setUp(self):
  self.assertIsNotNone(importlib.util.find_spec('native_input_pivot_refine'),'Wheel pivot refinement is missing')
  self.m=importlib.import_module('native_input_pivot_refine')
  root=Path(__file__).parent/'fixtures/native_palette'
  self.session=load_local_palette_session(root/json.loads(read_local_fixture_text(root/'manifest.json'))['snapshots'][1])
  self.reference=self.session['initial_pose'];self.geometry=InputGeometry((757,428,1287,958),(624,624))
  self.settings=InputSettings(.5,3,5,.1,.01)
  self.rules=[dict(enabled=True,exact=True,colors=[c],tolerance=0) for c in ['#D8866E','#D0D2B4','#768A60']]
  self.route=[wheel_gesture(self.geometry.board,1,(1022,693)).record(),
              wheel_gesture(self.geometry.board,-1,(1050,693)).record()]

 def refine(self,routes,**kwargs):
  return self.m.refine_native_wheel_pivots(self.session,routes,self.reference,self.geometry,self.settings,
    self.rules,sample_policy='all_recorded_points',wheel_delta_per_step=1.,now=0.,deadline=120.,**kwargs)

 def test_pivot_edit_can_hit_without_adding_scale_drift(self):
  # Target comes from independently recorded finite probe: second pivot1054,693.
  before=json.dumps(self.route,sort_keys=True)
  result=self.refine([self.route],pixel_steps=(4,1),beam_width=1,max_candidates=100)
  best=result['candidates'][0]
  self.assertEqual(best['prediction']['colors'],['#D8866E','#D0D2B4','#768A60'])
  self.assertTrue(best['prediction']['predicted_accepted'])
  self.assertEqual(len(best['input_route']),2)
  self.assertAlmostEqual(best['final_pose']['scale'],.9998999834,places=9)
  self.assertEqual(json.dumps(self.route,sort_keys=True),before)
  replay=replay_native_route(self.reference,best['input_route'],self.geometry,self.settings,
                sample_policy='all_recorded_points',wheel_delta_per_step=1.)
  self.assertEqual(replay['final_pose'],best['final_pose'])
  self.assertFalse(best['game_response_verified'])

 def test_exact_old_route_is_retained(self):
  exact=[self.route[0],wheel_gesture(self.geometry.board,-1,(1054,693)).record()]
  result=self.refine([exact])
  self.assertTrue(result['candidates'][0]['prediction']['predicted_accepted'])
  self.assertEqual(result['candidates'][0]['input_route'],exact)

 def test_common_pair_pivot_edits_are_evaluated(self):
  result=self.refine([self.route],pixel_steps=(1,),beam_width=1,max_candidates=100)
  self.assertGreater(result['evaluations_by_kind'].get('pair_common',0),0)
  self.assertTrue(all(len(r['input_route'])==2 for r in result['candidates']))

 def test_no_wheel_routes_and_duplicates_keep_shortest_identity(self):
  zero=wheel_gesture(self.geometry.board,0).record()
  result=self.refine([[zero],[]],pixel_steps=(1,))
  self.assertEqual(result['candidates'][0]['input_route'],[])
  self.assertGreater(result['duplicate_endpoints'],0)
  self.assertEqual(result['stop_reason'],'no_editable_wheels')

 def test_candidate_time_limits_and_cancel_fail_closed(self):
  result=self.refine([self.route],max_candidates=1)
  self.assertEqual(result['evaluated'],1)
  self.assertEqual(result['stop_reason'],'candidate_limit')
  def stop():raise InterruptedError('F9')
  with self.assertRaises(InterruptedError):self.refine([self.route],check=stop)
  result=self.m.refine_native_wheel_pivots(self.session,[self.route],self.reference,self.geometry,self.settings,
    self.rules,sample_policy='all_recorded_points',wheel_delta_per_step=1.,now=5.,deadline=5.)
  self.assertEqual(result['candidates'],[])
  self.assertEqual(result['stop_reason'],'deadline')

 def test_reference_sampling_and_steps_are_validated(self):
  for steps in ((),(0,),(1.5,),(10000,)):
   with self.assertRaises(ValueError):self.refine([self.route],pixel_steps=steps)
  other=dict(self.reference,scale=1.01)
  with self.assertRaises(ValueError):
   self.m.refine_native_wheel_pivots(self.session,[self.route],other,self.geometry,self.settings,
     self.rules,sample_policy='all_recorded_points',wheel_delta_per_step=1.,now=0.,deadline=120.)

 def test_search_cannot_spend_execution_reserve(self):
  result=self.m.refine_native_wheel_pivots(self.session,[self.route],self.reference,self.geometry,self.settings,
    self.rules,sample_policy='all_recorded_points',wheel_delta_per_step=1.,now=0.,deadline=2.)
  self.assertEqual(result['candidates'],[])

 def test_outside_seed_and_sparse_sampling_are_rejected(self):
  bad=json.loads(json.dumps(self.route));bad[0]['points']=[[0,0]]
  with self.assertRaises(ValueError):self.refine([bad])
  with self.assertRaises(ValueError):
   self.m.refine_native_wheel_pivots(self.session,[self.route],self.reference,self.geometry,self.settings,
    self.rules,sample_policy='explicit_indices',wheel_delta_per_step=1.,now=0.,deadline=120.)

 def test_explicit_two_dimensional_grid_escapes_pattern_plateau(self):
  rules=[dict(enabled=True,exact=True,colors=[c],tolerance=0) for c in ['#61788D','#F1D4B0','#6F524A']]
  # Frozen finite probe from the saved session, no recorded target pose.
  from input_gestures import drag_gesture
  route=[drag_gesture(self.geometry.board,-104,-6).record(),
         wheel_gesture(self.geometry.board,-1,(916,571)).record()]
  baseline=self.m.refine_native_wheel_pivots(self.session,[route],self.reference,self.geometry,self.settings,
   rules,sample_policy='all_recorded_points',wheel_delta_per_step=1.,now=0.,deadline=120.,
   pixel_steps=(1,),beam_width=1,max_candidates=10)
  self.assertEqual(baseline['candidates'][0]['prediction']['rank'][1],1.)
  result=self.m.refine_native_wheel_pivots(self.session,[route],self.reference,self.geometry,self.settings,
   rules,sample_policy='all_recorded_points',wheel_delta_per_step=1.,now=0.,deadline=120.,
   pixel_steps=(1,),beam_width=1,max_candidates=5000,time_budget_seconds=8.,pivot_grid_radius=32)
  self.assertTrue(result['candidates'][0]['prediction']['predicted_accepted'])
  self.assertEqual(len(result['candidates'][0]['input_route']),2)
  self.assertGreater(result['evaluations_by_kind'].get('single_pivot_grid',0),0)
  self.assertFalse(result['game_response_verified'])

 def test_grid_radius_is_bounded_and_charges_candidate_limit(self):
  for radius in (-1,1.5,33):
   with self.assertRaises(ValueError):self.refine([self.route],pivot_grid_radius=radius)
  result=self.refine([self.route],pixel_steps=(1,),pivot_grid_radius=32,max_candidates=2)
  self.assertLessEqual(result['evaluated'],2)
  self.assertEqual(result['stop_reason'],'candidate_limit')

if __name__=='__main__':unittest.main()
