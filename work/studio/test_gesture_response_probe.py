from types import SimpleNamespace
import unittest
import numpy as np
from atlas_pose import homogeneous
from gesture_response_probe import (response_probe_plan,run_response_probe,
                                    translation_shared_plan,zoom_probe_anchors,
                                    zoom_reversibility_plan)


class ProbeGame:
    def __init__(self):
        self.pose=np.eye(3);self.until=1000.;self.stage_until=1000.
        self.now=70.;self.inputs=[];self.releases=[];self.stopped=False
        self.fail_input=False;self.changed=False
    def check(self):
        if self.stopped:raise InterruptedError('F9')
    def geometry(self):return (0,0,1280,960 if not self.changed else 970)
    def perform_gesture(self,gesture):
        self.inputs.append(gesture)
        if self.fail_input:raise RuntimeError('input failed')
        if gesture.kind=='rotate':
            angle=np.radians(gesture.requested_angle*.97);scale=1.
        else:
            angle=0.;scale=(1.01 if gesture.wheel_steps>0 else .99)**abs(gesture.wheel_steps)
        matrix=scale*np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
        pivot=np.asarray(gesture.anchor)-[100,300]
        self.pose=homogeneous(np.c_[matrix,pivot-matrix@pivot])@self.pose
        self.now+=gesture.duration
    def pause(self,seconds):self.now+=seconds;self.check()
    def move_to(self,point):self.check()
    def send(self,value):self.releases.append(value)


class ResponseProbeTests(unittest.TestCase):
    def setUp(self):
        self.game=ProbeGame();self.events=[];self.frames={}
        self.scene=SimpleNamespace(board=(100,300,598,798),
                                   markers=((180,450),(350,680),(510,570)))
    def snap(self,name,scene):
        self.frames[name]=self.game.pose.copy()
        return self.frames[name]
    def register(self,a,b,scene,diagnostics):
        return dict(matrix=(b@np.linalg.inv(a))[:2].tolist())
    def run_probe(self,register=None,protocol='baseline'):
        return run_response_probe(self.game,self.scene,np.eye(3),self.snap,
                lambda k,**d:self.events.append(dict(kind=k,**d)),
                register=register or self.register,clock=lambda:self.game.now,protocol=protocol)

    def test_plan_repeats_integer_inputs_for_both_pivots_and_wheel_directions(self):
        plan=response_probe_plan(self.scene.board)
        self.assertEqual(len(plan),28)
        for first,second in zip(plan[:14],plan[14:]):
            self.assertEqual(first.gesture,second.gesture)
            self.assertNotEqual(first.repeat,second.repeat)
            for point in first.gesture.points:
                self.assertTrue(all(isinstance(v,int) for v in point))
        self.assertEqual({p.anchor_name for p in plan},{'center','offset'})
        self.assertEqual([p.gesture.wheel_steps for p in plan if p.gesture.kind=='wheel'],[-1,1,-1,1])

    def test_translation_shared_plan_is_bounded_and_uses_real_drag_gestures(self):
        plan = translation_shared_plan(self.scene.board, cycles=2)
        self.assertEqual(len(plan), 20)
        self.assertEqual({p.anchor_name for p in plan}, {'center', 'offset'})
        self.assertEqual(sum(p.gesture.kind == 'drag' for p in plan), 16)
        self.assertEqual([p.gesture.wheel_steps for p in plan if p.gesture.kind == 'wheel'],
                         [-1, 1, -1, 1])
        self.assertTrue(all(p.gesture.has_effect for p in plan))

    def test_translation_shared_probe_runs_without_recorder(self):
        _, result = run_response_probe(
            self.game, self.scene, np.eye(3), self.snap,
            lambda k, **d: self.events.append(dict(kind=k, **d)),
            register=self.register, clock=lambda: self.game.now,
            probe_plan='translation_shared', probe_cycles=1)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['planned'], 10)
        self.assertEqual(result['completed'], 10)
        self.assertEqual(len(self.game.inputs), 10)
        self.assertEqual(self.game.releases, [4, 16])

    def test_zoom_reversibility_plan_covers_anchor_pairs_and_both_orders(self):
        board=self.scene.board
        plan=zoom_reversibility_plan(board)
        self.assertEqual(len(plan),36)  # 3 cycles × 3 anchors × 2 pairs × 2 inputs
        self.assertEqual({p.anchor_name for p in plan},{'center','offset','edge'})
        self.assertEqual({p.direction for p in plan},{-1,1})
        for cycle in range(1,4):
            for anchor in ('center','offset','edge'):
                rows=[p for p in plan if p.cycle==cycle and p.anchor_name==anchor]
                self.assertEqual([(p.phase,p.direction) for p in rows],
                                 [('forward',1),('return',-1),
                                  ('forward',-1),('return',1)])
                self.assertEqual(rows[0].gesture.anchor,zoom_probe_anchors(board)[anchor])

    def test_zoom_reversibility_plan_accepts_selected_anchors_and_cycles(self):
        plan=zoom_reversibility_plan(self.scene.board,cycles=2,anchors=('edge','center'))
        self.assertEqual(len(plan),16)
        self.assertEqual([p.anchor_name for p in plan[:4]],['edge']*4)
        self.assertEqual([p.anchor_name for p in plan[4:8]],['center']*4)
        self.assertEqual([p.anchor_name for p in plan[8:12]],['center']*4)
        self.assertEqual([p.anchor_name for p in plan[12:]],['edge']*4)
        with self.assertRaises(ValueError):zoom_reversibility_plan(self.scene.board,cycles=0)
        with self.assertRaises(ValueError):zoom_reversibility_plan(self.scene.board,anchors=('bad',))

    def test_zoom_reversibility_probe_records_each_step_and_pair(self):
        _, result = run_response_probe(
            self.game, self.scene, np.eye(3), self.snap,
            lambda k, **d: self.events.append(dict(kind=k, **d)),
            register=self.register, clock=lambda: self.game.now,
            protocol='zoom_reversibility', probe_cycles=1,
            probe_anchors=('center',))
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['completed'], 4)
        self.assertEqual(result['completed_pairs'], 2)
        rows=[e for e in self.events if e['kind']=='zoom_reversibility_measurement']
        self.assertEqual([(r['phase'],r['direction']) for r in rows],
                         [('forward',1),('return',-1),('forward',-1),('return',1)])
        pairs=[e for e in self.events if e['kind']=='zoom_reversibility_pair']
        self.assertEqual(len(pairs),2)
        self.assertTrue(all('net' in p for p in pairs))
        self.assertEqual(self.game.releases,[4,16])

    def test_complete_uses_measured_state_and_never_assumes_wheel_return(self):
        frame,result=self.run_probe()
        self.assertEqual(result['status'],'complete')
        self.assertEqual(result['completed'],len(self.game.inputs))
        np.testing.assert_allclose(result['measured_pose'],self.game.pose[:2],atol=1e-10)
        self.assertFalse(np.allclose(self.game.pose,np.eye(3)))
        self.assertEqual(self.game.releases,[4,16])
        self.assertFalse(result['response_model_installed'])
        self.assertGreater(self.game.now,60.)
        self.assertEqual(len(self.frames),2*result['completed'])
        self.assertFalse(self.game.capture_input_trace)

    def test_real_deadline_prevents_input_and_releases(self):
        self.game.until=self.game.now+1
        _,result=self.run_probe()
        self.assertEqual(result['status'],'game_time_remaining')
        self.assertFalse(self.game.inputs)
        self.assertEqual(self.game.releases,[4,16])

    def test_f9_after_first_input_propagates_and_releases(self):
        perform=self.game.perform_gesture
        def stop(gesture):perform(gesture);self.game.stopped=True
        self.game.perform_gesture=stop
        with self.assertRaisesRegex(InterruptedError,'F9'):self.run_probe()
        self.assertEqual(len(self.game.inputs),1)
        self.assertEqual(self.game.releases,[4,16])
        self.assertFalse(self.game.capture_input_trace)

    def test_comparison_records_both_variants_and_uses_identical_sender(self):
        _,result=self.run_probe(protocol='rotation_compare')
        self.assertEqual(result['status'],'complete')
        self.assertEqual(result['completed'],32)
        measurements=[r for r in self.events if r['kind']=='response_probe_measurement']
        self.assertEqual(len(measurements),32)
        self.assertEqual({r['variant'] for r in measurements},{'legacy','grouped'})
        self.assertEqual(len([r for r in self.events if r['kind']=='response_probe_input']),32)
        self.assertEqual(self.game.releases,[4,16])
        self.assertFalse(self.game.capture_input_trace)

    def test_geometry_change_propagates_without_another_input(self):
        snap=self.snap
        def changed(name,scene):
            frame=snap(name,scene)
            self.game.changed=True
            return frame
        self.snap=changed
        with self.assertRaisesRegex(InterruptedError,'geometry'):self.run_probe()
        self.assertEqual(len(self.game.inputs),1)
        self.assertEqual(self.game.releases,[4,16])

    def test_missing_registration_or_exception_preserves_partial_data(self):
        for throws in (False,True):
            with self.subTest(throws=throws):
                self.setUp()
                def missing(*args):
                    if throws:raise ValueError('no texture')
                    return None
                _,result=self.run_probe(register=missing)
                self.assertEqual(result['status'],'registration_incomplete')
                self.assertIsNone(result['measured_pose'])
                self.assertEqual(len(self.game.inputs),1)
                self.assertEqual(len(self.frames),2)
                record=next(e for e in self.events if e['kind']=='response_probe_measurement')
                self.assertFalse(record['registration_complete'])
                if throws:self.assertIn('error',record['diagnostics']['forward'])
                self.assertEqual(self.game.releases,[4,16])

    def test_input_exception_records_partial_outcome_without_retry(self):
        self.game.fail_input=True
        _,result=self.run_probe()
        self.assertEqual(result['status'],'measurement_failed')
        self.assertIsNone(result['measured_pose'])
        self.assertEqual(len(self.game.inputs),1)
        self.assertEqual(self.game.releases,[4,16])

    def test_visible_motion_is_reported_without_claiming_precision(self):
        calls=[]
        def moving(a,b,scene,diagnostics):
            calls.append(1)
            if len(calls)==3:return dict(matrix=[[1,0,2],[0,1,0]])
            return self.register(a,b,scene,diagnostics)
        _,result=self.run_probe(register=moving)
        self.assertEqual(result['status'],'texture_still_moving')
        self.assertFalse(result['response_model_installed'])
        self.assertEqual(len(self.game.inputs),1)

    def test_probe_frames_cannot_be_used_as_an_atlas_capture(self):
        from analyze_live_atlas import frame_sequence
        for event in (dict(kind='response_probe_plan'),
                      dict(kind='CAPTURE_COMPLETE',strategy='response')):
            with self.assertRaisesRegex(ValueError,'diagnostic'):
                frame_sequence([dict(kind='frame',name='max_sampling'),event])


if __name__=='__main__':unittest.main()
