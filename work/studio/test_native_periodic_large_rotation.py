"""Global approaches keep large safe rotations and measured small corrections."""
import inspect,math,unittest
import numpy as np
from input_gestures import grouped_rotation_gesture
from native_input_compile import compile_native_route
from native_input_response import InputGeometry,InputSettings,replay_native_route
from native_periodic_route import compile_periodic_approach
from native_live.project_closed_loop_io import validate_research_gesture


class PeriodicLargeRotationTests(unittest.TestCase):
    def setUp(self):
        self.geometry=InputGeometry((100,100,800,800),(624,624),'windows_legacy_mouse_pixels')
        self.settings=InputSettings(.5,3.,0.,.1,.01)
        self.reference=dict(position=[0.,0.],scale=1.,rotation_degrees=0.)
        self.markers=[[216.,500.],[450.,600.],[680.,470.]]
        self.target=dict(position=[.190616,-.016095],scale=.674013,rotation_degrees=126.94257)

    def approach(self,target=None,reference=None):
        # A fixed clock isolates finite work from host load. Real-time timing
        # is checked separately by the archived-session replay benchmark.
        return compile_periodic_approach(target or self.target,reference or self.reference,
            self.geometry,self.settings,self.markers,wheel_delta_per_step=1.,
            time_budget_seconds=2.,clock=lambda:0.)

    def test_global_126_degree_approach_uses_complete_short_safe_sequence(self):
        result=self.approach()
        self.assertLessEqual(len(result['input_route']),8)
        self.assertLessEqual(result['actions']['rotate'],3)
        self.assertLess(result['final_marker_error'],.6)
        self.assertTrue(any(abs(g['requested_angle'])>12 for g in result['input_route'] if g['kind']=='rotate'))
        for record in result['input_route']:
            validate_research_gesture(record,self.geometry.board)
            if record['kind']=='rotate':self.assertLessEqual(abs(record['requested_angle']),90.)
        replay=replay_native_route(self.reference,result['input_route'],self.geometry,self.settings,
            sample_policy='all_recorded_points',wheel_delta_per_step=1.)
        self.assertEqual(replay['final_pose'],result['final_pose'])
        self.assertFalse(result['execution_verified'])

    def test_large_rotation_keeps_small_angle_fallback_and_does_not_certify_hex(self):
        tiny=dict(self.reference,rotation_degrees=.3,position=[.0002,-.0001])
        result=self.approach(tiny)
        self.assertTrue(result['model_progress'])
        self.assertLess(result['final_marker_error'],result['initial_marker_error'])
        self.assertTrue(all(abs(g['requested_angle'])<=12. for g in result['input_route'] if g['kind']=='rotate'))
        self.assertFalse(result['game_response_verified'])

    def test_generic_compiler_remains_limited_to_twelve_unless_opted_in(self):
        self.assertEqual(inspect.signature(compile_native_route).parameters['max_rotation_degrees'].default,12.)
        result=compile_native_route(self.target,self.reference,self.geometry,self.settings,self.markers,
            wheel_delta_per_step=1.,sample_policy='all_recorded_points',now=0.,deadline=120.,
            planning_seconds=2.,clock=lambda:0.)
        self.assertTrue(result['input_route'])
        self.assertTrue(all(abs(g['requested_angle'])<=12. for g in result['input_route'] if g['kind']=='rotate'))

    def test_large_rotation_cap_rejects_nonfinite_and_outside_standard_range(self):
        for cap in (0.,-12.,90.01,math.nan,math.inf):
            with self.subTest(cap=cap),self.assertRaises(ValueError):
                compile_native_route(self.target,self.reference,self.geometry,self.settings,self.markers,
                    wheel_delta_per_step=1.,sample_policy='all_recorded_points',now=0.,deadline=120.,
                    max_rotation_degrees=cap)

    def test_global_deadline_and_cancellation_remain_enforced(self):
        ticks=iter([0.,0.,1.,1.,1.,1.])
        result=compile_periodic_approach(self.target,self.reference,self.geometry,self.settings,self.markers,
            wheel_delta_per_step=1.,time_budget_seconds=.1,clock=lambda:next(ticks,1.))
        self.assertEqual(result['reason'],'deadline')
        self.assertEqual(result['input_route'],[])
        calls=[0]
        def stop():
            calls[0]+=1
            if calls[0]>2:raise InterruptedError('F9')
        with self.assertRaises(InterruptedError):
            compile_periodic_approach(self.target,self.reference,self.geometry,self.settings,self.markers,
                wheel_delta_per_step=1.,time_budget_seconds=2.,clock=lambda:0.,check=stop)

    def test_direct_90_degree_proposal_is_safe_and_replays_known_rotation(self):
        gesture=grouped_rotation_gesture((120,120,780,780),90.,(450,450)).record()
        validate_research_gesture(gesture,self.geometry.board)
        replay=replay_native_route(self.reference,[gesture],self.geometry,self.settings,
            sample_policy='all_recorded_points',wheel_delta_per_step=1.)
        self.assertAlmostEqual(abs(replay['final_pose']['rotation_degrees']),90.,delta=.1)
        # The known quarter-turn maps a point relative to the native pivot
        # to an orthogonal direction while preserving its radius.
        before=np.asarray([100.,50.]);angle=math.radians(replay['final_pose']['rotation_degrees'])
        after=np.array([[math.cos(angle),-math.sin(angle)],[math.sin(angle),math.cos(angle)]])@before
        self.assertAlmostEqual(float(np.linalg.norm(after)),float(np.linalg.norm(before)),places=6)
        self.assertLess(abs(float(before@after)),30.)

    def test_opted_in_compiler_still_obeys_step_and_proposal_limits(self):
        for options in (dict(max_steps=1),dict(max_proposals=1)):
            with self.subTest(options=options):
                result=compile_native_route(self.target,self.reference,self.geometry,self.settings,self.markers,
                    wheel_delta_per_step=1.,sample_policy='all_recorded_points',now=0.,deadline=120.,
                    planning_seconds=2.,clock=lambda:0.,max_rotation_degrees=90.,**options)
                if 'max_steps' in options:self.assertLessEqual(len(result['input_route']),options['max_steps'])
                if 'max_proposals' in options:self.assertLessEqual(result['evaluated_proposals'],options['max_proposals'])
                self.assertFalse(result['allowed'])


if __name__=='__main__':unittest.main()
