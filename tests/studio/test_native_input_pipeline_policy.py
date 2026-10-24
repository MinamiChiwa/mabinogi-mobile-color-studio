"""Disallowed endpoints must not hide allowed alternatives or end a search."""
import inspect,unittest
import test_native_input_pipeline as fixtures
from input_gestures import drag_gesture,wheel_gesture


class NativePipelinePolicyTests(unittest.TestCase):
 def setUp(self):
  self.f=fixtures.NativeInputPipelineTests();self.f.setUp()

 def require_filter(self):
  self.assertIn('route_filter',inspect.signature(self.f.m.search_native_input_pipeline).parameters,
                'Pipeline needs a retention policy before its exact-stop decision')

 def run_small(self,**kwargs):
  return self.f.run_pipeline(generate_target_seeds=False,max_coarse=1,shortlist=1,
      max_structural=1,macro_candidates=1,pivot_candidates=1,pivot_grid_radius=0,
      time_budget_seconds=.3,**kwargs)

 def test_filtered_exact_identity_does_not_stop_later_stages(self):
  self.require_filter()
  result=self.run_small(route_filter=lambda route:False)
  self.assertFalse(result['predicted_exact']);self.assertEqual(result['candidates'],[])
  self.assertIsNotNone(result['stages']['compile'])
  self.assertIsNotNone(result['stages']['structural'])

 def test_filtered_exact_seed_does_not_crowd_the_allowed_identity(self):
  self.require_filter();f=self.f
  route=[drag_gesture(f.geometry.board,-104,-6).record(),wheel_gesture(f.geometry.board,-1,(936,584)).record()]
  f.rules=[dict(enabled=True,exact=True,colors=[c],tolerance=0) for c in ['#61788D','#F1D4B0','#6F524A']]
  result=self.run_small(seed_bundle=f.bind([route]),route_filter=lambda route:not route,top_k=1)
  self.assertEqual(len(result['candidates']),1)
  self.assertEqual(result['candidates'][0]['input_route'],[])
  self.assertFalse(result['candidates'][0]['prediction']['predicted_accepted'])
  self.assertIsNotNone(result['stages']['compile'])

 def test_filter_time_is_charged_and_late_exact_endpoint_is_discarded(self):
  self.require_filter();tick=[0.]
  def slow_filter(route):tick[0]=2.;return True
  result=self.run_small(route_filter=slow_filter,clock=lambda:tick[0])
  self.assertEqual(result['candidates'],[])
  self.assertEqual(result['stop_reason'],'deadline')

 def test_nonboolean_policy_and_cancellation_are_not_silently_coerced(self):
  self.require_filter()
  with self.assertRaises(ValueError):self.run_small(route_filter=lambda route:1)
  with self.assertRaises(ValueError):self.run_small(route_filter=True)
  def cancelled(route):raise InterruptedError('F9')
  with self.assertRaises(InterruptedError):self.run_small(route_filter=cancelled)


if __name__=='__main__':unittest.main()
