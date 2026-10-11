"""Verified DPI lattices are accepted while unproven viewport math stays blocked."""
import unittest

from native_live.read_dye_input_backend import viewport_mapping_is_verified


class NativeInputBackendMappingTests(unittest.TestCase):
    def test_one_to_one_viewport_remains_supported_without_lattice(self):
        self.assertTrue(viewport_mapping_is_verified([0, 0], [1., 1.], None))

    def test_verified_target_awareness_lattice_allows_scaled_viewport(self):
        mapping = dict(source='win32_target_awareness_pixel_lattice',
                       coordinate_validation=dict(verified=True),
                       mapping_sha256='bound-map')
        self.assertTrue(viewport_mapping_is_verified([3, 4], [.8, 1.25], mapping))

    def test_unverified_or_malformed_mapping_stays_rejected(self):
        mappings = (
            None,
            {},
            dict(source='win32_target_awareness_pixel_lattice',
                 coordinate_validation=dict(verified=False)),
            dict(source='other', coordinate_validation=dict(verified=True)),
        )
        for mapping in mappings:
            with self.subTest(mapping=mapping):
                self.assertFalse(viewport_mapping_is_verified([3, 4], [.8, 1.25], mapping))


if __name__ == '__main__': unittest.main()
