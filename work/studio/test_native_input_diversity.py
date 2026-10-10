"""Keep different scale/angle regions in a finite route-search frontier."""
from test_support import read_local_fixture_text
from test_support import load_local_palette_session
import importlib,json,unittest
from pathlib import Path
from native_input_response import InputGeometry,InputSettings,replay_native_route
from native_palette_scoring import load_session,score_native_pose
from input_gestures import wheel_gesture


class NativeInputDiversityTests(unittest.TestCase):
 def setUp(self):
  self.m=importlib.import_module('native_input_route_search')
  root=Path(__file__).parent/'fixtures/native_palette'
  self.session=load_local_palette_session(root/json.loads(read_local_fixture_text(root/'manifest.json'))['snapshots'][1])
  self.geometry=InputGeometry((757,428,1287,958),(624,624));self.settings=InputSettings(.5,3,5,.1,.01)

 def test_frontier_retains_other_scale_region_before_same_region_runnerup(self):
  self.assertTrue(hasattr(self.m,'_select_frontier'))
  # Literal rankings model multiple slightly different positions in one region.
  rows=[dict(candidate='a',prediction=dict(rank=(True,1,1,1)),needed=4,input_route=[],
             final_pose=dict(position=[0,0],scale=.99,rotation_degrees=0)),
        dict(candidate='b',prediction=dict(rank=(True,2,1,2)),needed=4,input_route=[],
             final_pose=dict(position=[.01,0],scale=.99,rotation_degrees=0)),
        dict(candidate='c',prediction=dict(rank=(True,5,1,5)),needed=4,input_route=[],
             final_pose=dict(position=[0,0],scale=1,rotation_degrees=0))]
  rank=lambda r:(*r['prediction']['rank'],r['needed'],len(r['input_route']))
  selected=self.m._select_frontier(rows,2,rank,'scale_angle_diverse',.005,.5)
  self.assertEqual([r['candidate'] for r in selected],['a','c'])
  self.assertEqual([r['candidate'] for r in self.m._select_frontier(rows,2,rank,'rank_only',.005,.5)],['a','b'])

 def test_diverse_search_replays_actual_routes_and_keeps_seed_best(self):
  rules=[dict(enabled=True,exact=True,colors=[c],tolerance=0) for c in ['#D8866E','#D0D2B4','#768A60']]
  result=self.m.search_native_input_routes(self.session,[[]],self.session['initial_pose'],self.geometry,
   self.settings,rules,sample_policy='all_recorded_points',wheel_delta_per_step=1.,now=0.,deadline=120.,
   max_depth=1,max_candidates=300,frontier_policy='scale_angle_diverse')
  best=result['candidates'][0]
  self.assertTrue(best['prediction']['predicted_accepted'])
  self.assertEqual(result['frontier_policy'],'scale_angle_diverse')
  replay=replay_native_route(self.session['initial_pose'],best['input_route'],self.geometry,self.settings,
   sample_policy='all_recorded_points',wheel_delta_per_step=1.)
  self.assertEqual(replay['final_pose'],best['final_pose'])
  self.assertFalse(result['game_response_verified'])

 def test_invalid_policy_and_bin_sizes_are_rejected(self):
  rules=[dict(enabled=True,exact=True,colors=['#000000'],tolerance=0)]*3
  for kw in (dict(frontier_policy='unknown'),dict(scale_bin_width=0),dict(angle_bin_degrees=float('nan'))):
   with self.assertRaises(ValueError):
    self.m.search_native_input_routes(self.session,[[]],self.session['initial_pose'],self.geometry,
     self.settings,rules,sample_policy='all_recorded_points',wheel_delta_per_step=1.,now=0.,deadline=120.,**kw)

if __name__=='__main__':unittest.main()
