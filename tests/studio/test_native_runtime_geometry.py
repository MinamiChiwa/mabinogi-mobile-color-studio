"""TDD contract for measured runtime RectTransform geometry."""
import importlib, importlib.util, unittest
import numpy as np


class NativeRuntimeGeometryTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('native_runtime_geometry'))
        self.m=importlib.import_module('native_runtime_geometry')
        self.board=(757.,428.,1287.,958.)
        self.local=(624.,624.)
        self.samples=[
            dict(screen=[757.,428.],local=[-312.,312.]),
            dict(screen=[1287.,428.],local=[312.,312.]),
            dict(screen=[757.,958.],local=[-312.,-312.]),
            dict(screen=[1287.,958.],local=[312.,-312.]),
        ]

    def test_valid_runtime_rect_transform_yields_input_geometry(self):
        evidence=self.m.validate_runtime_geometry(
            dict(source='runtime_recttransform',camera='null',screen_bounds=list(self.board),
                 local_size=list(self.local),samples=self.samples))
        self.assertEqual(evidence['source'],'runtime_recttransform')
        self.assertLessEqual(evidence['max_residual_local'],1e-6)
        geometry=evidence['input_geometry']
        self.assertEqual(geometry.board,self.board)
        self.assertEqual(geometry.local_size,self.local)
        self.assertTrue(np.allclose(geometry.local([1022.,693.]),[0.,0.]))

    def test_screen_to_local_preserves_y_up_and_rejects_perspective_samples(self):
        evidence=self.m.validate_runtime_geometry(
            dict(source='runtime_recttransform',camera='null',screen_bounds=list(self.board),
                 local_size=list(self.local),samples=self.samples))
        self.assertTrue(np.allclose(evidence['input_geometry'].local([757.,958.]),[-312.,-312.]))
        bad=[dict(row) for row in self.samples];bad[3]=dict(screen=[1287.,958.],local=[313.,-312.])
        with self.assertRaises(ValueError):
            self.m.validate_runtime_geometry(dict(source='runtime_recttransform',camera='null',
                 screen_bounds=list(self.board),local_size=list(self.local),samples=bad))

    def test_prefab_or_screenshot_sources_are_rejected(self):
        for source in ('prefab','screenshot','assumed'):
            with self.assertRaises(ValueError):
                self.m.validate_runtime_geometry(dict(source=source,camera='null',
                    screen_bounds=list(self.board),local_size=list(self.local),samples=self.samples))

    def test_missing_corners_nonfinite_and_bad_camera_fail_closed(self):
        base=dict(source='runtime_recttransform',camera='null',screen_bounds=list(self.board),
                  local_size=list(self.local),samples=self.samples)
        for change in (dict(samples=self.samples[:3]),dict(camera='main_camera'),
                      dict(screen_bounds=[1.,2.,1.,4.]),dict(local_size=[624.,0.])):
            with self.assertRaises(ValueError):self.m.validate_runtime_geometry(dict(base,**change))
        bad=[dict(row) for row in self.samples];bad[0]['local']=[float('nan'),0.]
        with self.assertRaises(ValueError):self.m.validate_runtime_geometry(dict(base,samples=bad))

    def test_tolerance_is_finite_nonnegative_and_cancel_propagates(self):
        base=dict(source='runtime_recttransform',camera='null',screen_bounds=list(self.board),
                  local_size=list(self.local),samples=self.samples)
        for tolerance in (-1.,float('nan'),float('inf')):
            with self.assertRaises(ValueError):self.m.validate_runtime_geometry(dict(base,tolerance=tolerance))
        def stop():raise InterruptedError('F9')
        with self.assertRaises(InterruptedError):self.m.validate_runtime_geometry(base,check=stop)

    def test_duplicate_corners_cannot_pass_as_four_corner_measurement(self):
        for samples in ([self.samples[0]]*4,[self.samples[0],self.samples[1],self.samples[2],self.samples[2]]):
            with self.assertRaises(ValueError):
                self.m.validate_runtime_geometry(dict(source='runtime_recttransform',camera='null',
                    screen_bounds=self.board,local_size=self.local,samples=samples))

    def test_permuted_corners_preserve_measured_mapping(self):
        result=self.m.validate_runtime_geometry(dict(source='runtime_recttransform',camera='null',
            screen_bounds=self.board,local_size=self.local,samples=self.samples[::-1]))
        self.assertTrue(result['mapping_consistent'])
        self.assertFalse(result['runtime_measurement_verified'])

    def test_excessive_tolerance_cannot_bypass_geometry_check(self):
        with self.assertRaises(ValueError):
            self.m.validate_runtime_geometry(dict(source='runtime_recttransform',camera='null',
                screen_bounds=self.board,local_size=self.local,samples=self.samples,tolerance=1000))


if __name__=='__main__':unittest.main()
