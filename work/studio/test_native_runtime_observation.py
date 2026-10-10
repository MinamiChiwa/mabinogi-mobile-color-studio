"""Validate live-observation records before any future input consumer."""
import importlib, importlib.util, unittest


class NativeRuntimeObservationTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('native_runtime_observation'))
        self.m=importlib.import_module('native_runtime_observation')
        self.base=dict(
            active=True,
            build_sha256='a'*64, pid=123, process_creation_token=99,
            capture_id='capture', session_token='session',
            pixel_sha256=('b'*64,'c'*64,'d'*64),
            pose=dict(position=[0.,0.],scale=1.,rotation_degrees=0.),
            animator=dict(position=dict(is_done=True,stop_requested=False,elapsed=0.,duration=0.,last=[0.,0.],target=[0.,0.]),
                          rotation=dict(is_done=True,stop_requested=False,elapsed=0.,duration=0.,last=0.,target=0.)),
            geometry=dict(board=[757.,428.,1287.,958.],local_size=[624.,624.],camera='null',source='runtime_recttransform'),
            settings=dict(minimum_scale=.5,maximum_scale=3.,move_threshold=5.,move_tolerance=.1,scroll_zoom_ratio=.01),
            scroll=dict(project_delta=1.,game_delta=1.,sign_verified=True,observed_events=1),
            monotonic_time=1.)

    def test_valid_observation_and_stable_pair(self):
        obs=self.m.validate_observation(self.base)
        pair=self.m.validate_stable_pair(obs,dict(self.base,monotonic_time=1.2))
        self.assertTrue(pair['stable'])
        self.assertTrue(pair['animators_done'])
        self.assertEqual(pair['session_token'],'session')
        self.assertFalse(pair['execution_verified'])

    def test_mismatched_session_build_pixels_or_process_rejected(self):
        for key,value in (('session_token','other'),('build_sha256','e'*64),
                          ('pixel_sha256',('b'*64,'c'*64,'x'*64)),('pid',124),
                          ('process_creation_token',100)):
            with self.assertRaises(ValueError):
                self.m.validate_stable_pair(self.base,dict(self.base,**{key:value, 'monotonic_time':1.2}))

    def test_stability_requires_done_animators_and_close_pose(self):
        for change in (
            dict(animator=dict(position=dict(is_done=False,stop_requested=False,elapsed=0.,duration=1.,last=[0.,0.],target=[1.,0.]),
                                rotation=self.base['animator']['rotation'])),
            dict(pose=dict(position=[.01,0.],scale=1.,rotation_degrees=0.)),
            dict(monotonic_time=1.),
        ):
            second=dict(self.base,**change)
            with self.assertRaises(ValueError):
                self.m.validate_stable_pair(self.m.validate_observation(self.base),second)

    def test_incomplete_geometry_scroll_or_unbounded_numbers_fail(self):
        for change in (
            dict(geometry=dict(board=[1,2,3,4],local_size=[624,624],camera='null',source='screenshot')),
            dict(scroll=dict(project_delta=1.,game_delta=1.,sign_verified=False,observed_events=0)),
            dict(pose=dict(position=[float('nan'),0.],scale=1.,rotation_degrees=0.)),
        ):
            with self.assertRaises(ValueError):self.m.validate_observation(dict(self.base,**change))

    def test_cancelled_or_stale_observation_fails_closed(self):
        with self.assertRaises(ValueError):
            self.m.validate_observation(dict(self.base,active=False))
        with self.assertRaises(ValueError):
            self.m.validate_observation(dict(self.base,monotonic_time=0.))

    def test_nonfinite_animator_scalars_and_wrong_vector_shapes_reject(self):
        import copy
        for name,key,value in (('rotation','last',float('nan')),('rotation','target',float('inf')),
                               ('position','last',[0.]),('position','target',[0.,0.,0.])):
            record=copy.deepcopy(self.base);record['animator'][name][key]=value
            with self.assertRaises(ValueError):self.m.validate_observation(record)

    def test_unknown_active_and_zero_scroll_delta_reject(self):
        import copy
        unknown=copy.deepcopy(self.base);unknown.pop('active')
        with self.assertRaises(ValueError):self.m.validate_observation(unknown)
        for key in ('project_delta','game_delta'):
            record=copy.deepcopy(self.base);record['scroll'][key]=0.
            with self.assertRaises(ValueError):self.m.validate_observation(record)

    def test_invalid_stability_tolerances_cannot_make_drift_pass(self):
        for kw in (dict(position_tolerance=float('nan')),dict(scale_tolerance=-1),dict(rotation_tolerance=float('inf'))):
            with self.assertRaises(ValueError):self.m.validate_stable_pair(self.base,dict(self.base,monotonic_time=1.2),**kw)


if __name__=='__main__':unittest.main()
