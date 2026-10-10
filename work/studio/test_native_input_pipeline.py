"""Protect shared budgets, seed ownership, exact CPU endpoints and cancellation."""
from test_support import read_local_fixture_text
from test_support import load_local_palette_session
import importlib,importlib.util,json,unittest
from pathlib import Path
from dataclasses import replace
from itertools import chain,repeat
from unittest.mock import patch
from input_gestures import drag_gesture,wheel_gesture
from native_palette_scoring import load_session
from native_palette_search import PoseGrid
from native_input_response import InputGeometry,InputSettings,replay_native_route


class NativeInputPipelineTests(unittest.TestCase):
 def setUp(self):
  self.assertIsNotNone(importlib.util.find_spec('native_input_pipeline'),'Unified native input pipeline is missing')
  self.m=importlib.import_module('native_input_pipeline')
  root=Path(__file__).parent/'fixtures/native_palette'
  names=json.loads(read_local_fixture_text(root/'manifest.json'))['snapshots']
  self.session=load_local_palette_session(root/names[1]);self.other=load_local_palette_session(root/names[0])
  self.geometry=InputGeometry((757,428,1287,958),(624,624));self.settings=InputSettings(.5,3,5,.1,.01)
  self.rules=[dict(enabled=True,exact=True,colors=[c],tolerance=0) for c in ['#D7856D','#D0D2B4','#6D8354']]
  self.grid=PoseGrid((0.,0.),(0.,0.),1,1,(1.,),(0.,))

 def run_pipeline(self,**kw):
  return self.m.search_native_input_pipeline(self.session,self.grid,self.geometry,self.settings,self.rules,
       wheel_delta_per_step=1.,sample_policy='all_recorded_points',now=0.,deadline=120.,**kw)

 def bind(self,routes):
  return self.m.bind_native_route_seeds(self.session,self.geometry,self.settings,routes,
             wheel_delta_per_step=1.,sample_policy='all_recorded_points')

 def test_identity_returns_exact_without_spending_later_stage_budget(self):
  result=self.run_pipeline(time_budget_seconds=1.)
  best=result['candidates'][0]
  self.assertEqual(best['input_route'],[])
  self.assertTrue(best['prediction']['predicted_accepted'])
  self.assertEqual(result['stop_reason'],'predicted_exact')
  self.assertIsNone(result['stages']['macro'])
  self.assertFalse(result['game_response_verified'])

 def test_bound_exact_route_preserved_and_full_replay_matches(self):
  route=[drag_gesture(self.geometry.board,-104,-6).record(),wheel_gesture(self.geometry.board,-1,(936,584)).record()]
  self.rules=[dict(enabled=True,exact=True,colors=[c],tolerance=0) for c in ['#61788D','#F1D4B0','#6F524A']]
  bundle=self.bind([route]);original=json.dumps(bundle,sort_keys=True)
  result=self.run_pipeline(seed_bundle=bundle,time_budget_seconds=1.)
  best=result['candidates'][0]
  self.assertTrue(best['prediction']['predicted_accepted'])
  self.assertEqual(best['source'],'bound_saved_route')
  self.assertEqual(json.dumps(bundle,sort_keys=True),original)
  replay=replay_native_route(self.session['initial_pose'],best['input_route'],self.geometry,self.settings,
        sample_policy='all_recorded_points',wheel_delta_per_step=1.)
  self.assertEqual(replay['final_pose'],best['final_pose'])

 def test_cross_session_and_geometry_bindings_are_rejected(self):
  bundle=self.bind([[]])
  for session,geometry,settings,delta in ((self.other,self.geometry,self.settings,1.),
       (self.session,InputGeometry(self.geometry.board,(530,530)),self.settings,1.),
       (self.session,self.geometry,replace(self.settings,move_threshold=6),1.),
       (self.session,self.geometry,self.settings,-1.)):
   with self.assertRaises(ValueError):
    self.m.search_native_input_pipeline(session,self.grid,geometry,settings,self.rules,seed_bundle=bundle,
      wheel_delta_per_step=delta,sample_policy='all_recorded_points',now=0.,deadline=120.)

 def test_different_pointer_coordinate_convention_rejects_bound_seeds(self):
  corrected=InputGeometry(self.geometry.board,self.geometry.local_size,
                         input_coordinate_convention='windows_legacy_mouse_pixels')
  with self.assertRaises(ValueError):
   self.m.search_native_input_pipeline(self.session,self.grid,corrected,self.settings,self.rules,
    seed_bundle=self.bind([[]]),wheel_delta_per_step=1.,sample_policy='all_recorded_points',now=0.,deadline=120.)

 def test_copied_capture_id_cannot_hide_different_pixels(self):
  other=dict(self.other,capture_id=self.session['capture_id'],initial_pose=self.session['initial_pose'])
  with self.assertRaises(ValueError):
   self.m.search_native_input_pipeline(other,self.grid,self.geometry,self.settings,self.rules,
     seed_bundle=self.bind([[]]),wheel_delta_per_step=1.,sample_policy='all_recorded_points',now=0.,deadline=120.)

 def test_overall_deadline_stops_and_execution_reserve_is_preserved(self):
  ticks=chain([0.],repeat(2.))
  result=self.run_pipeline(time_budget_seconds=1.,clock=lambda:next(ticks))
  self.assertEqual(result['stop_reason'],'deadline')
  self.assertEqual(result['candidates'],[])
  result=self.m.search_native_input_pipeline(self.session,self.grid,self.geometry,self.settings,self.rules,
      wheel_delta_per_step=1.,sample_policy='all_recorded_points',now=0.,deadline=2.)
  self.assertEqual(result['candidates'],[])
  self.assertFalse(result['predicted_exact'])

 def test_all_explicit_stages_run_with_small_finite_limits(self):
  self.rules=[dict(enabled=True,exact=True,colors=['#000000'],tolerance=0)]*3
  result=self.run_pipeline(time_budget_seconds=2.,generate_target_seeds=False,shortlist=2,
      max_coarse=2,max_structural=2,macro_candidates=2,pivot_candidates=2,pivot_grid_radius=0)
  for name in ('coarse','compile','structural','macro','pivot'):
   self.assertIsNotNone(result['stages'][name],name)
  self.assertLessEqual(result['evaluated']['coarse'],2)
  self.assertLessEqual(result['evaluated']['structural'],2)
  self.assertFalse(result['execution_verified'])

 def test_invalid_limits_and_cancel_propagate(self):
  for kw in (dict(time_budget_seconds=0),dict(shortlist=0),dict(stage_fractions=(.4,)*6),dict(pivot_grid_radius=33)):
   with self.assertRaises(ValueError):self.run_pipeline(**kw)
  def stop():raise InterruptedError('F9')
  with self.assertRaises(InterruptedError):self.run_pipeline(check=stop)
  bad=[wheel_gesture(self.geometry.board,1).record()];bad[0]['points']=[[0,0]]
  with self.assertRaises(ValueError):self.bind([bad])

 def test_elapsed_initial_scoring_expires_exact_route_execution_budget(self):
  tick=[0.];score=self.m.score_native_pose
  def slow_score(*args,**kwargs):
   result=score(*args,**kwargs);tick[0]=118.;return result
  with patch.object(self.m,'score_native_pose',side_effect=slow_score):
   result=self.run_pipeline(time_budget_seconds=120.,clock=lambda:tick[0])
  self.assertEqual(result['candidates'],[])
  self.assertEqual(result['execution_seconds_remaining'],2.)
  self.assertFalse(result['predicted_exact'])

 def test_long_bound_seed_preparation_is_charged_to_search_limit(self):
  tick=[0.];binding=self.m._binding
  def slow_binding(*args,**kwargs):
   result=binding(*args,**kwargs);tick[0]=2.;return result
  with patch.object(self.m,'_binding',side_effect=slow_binding):
   result=self.run_pipeline(time_budget_seconds=1.,clock=lambda:tick[0])
  self.assertEqual(result['candidates'],[])
  self.assertEqual(result['stop_reason'],'deadline')
  self.assertEqual(result['elapsed_seconds'],2.)

 def test_unsupported_route_record_is_rejected_during_binding(self):
  bad=[wheel_gesture(self.geometry.board,1).record()];bad[0]['kind']='path'
  with self.assertRaises(ValueError):self.bind([bad])

 def test_bound_reference_change_is_rejected_even_with_same_capture_pixels(self):
  changed=dict(self.session,initial_pose=dict(self.session['initial_pose'],position=[.01,0.]))
  with self.assertRaises(ValueError):
   self.m.search_native_input_pipeline(changed,self.grid,self.geometry,self.settings,self.rules,
       seed_bundle=self.bind([[]]),wheel_delta_per_step=1.,sample_policy='all_recorded_points',now=0.,deadline=120.)

if __name__=='__main__':unittest.main()
