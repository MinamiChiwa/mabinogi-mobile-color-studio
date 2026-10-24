"""Undistributed private evidence skips, but present bad evidence fails."""
import json
from pathlib import Path
import tempfile
import unittest

from test_support import (requires_local_fixture, requires_native_case,
                          requires_palette_fixture, read_local_fixture_text)


class LocalFixtureGuardTests(unittest.TestCase):
    def test_missing_evidence_has_an_explicit_skip_reason(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'private-oracle.json'
            with self.assertRaisesRegex(unittest.SkipTest, 'not distributed: .*private-oracle.json'):
                requires_local_fixture(path)

    def test_existing_invalid_json_is_never_converted_to_skip(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'snapshot.json'; path.write_text('{broken', encoding='utf-8')
            with self.assertRaises(json.JSONDecodeError):
                requires_palette_fixture(folder)
            self.assertEqual(read_local_fixture_text(path), '{broken')

    def test_missing_pixel_names_the_actual_required_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'snapshot.json').write_text(json.dumps({'fragments': [{'pixel_file': 'fragment_1.png'}]}))
            with self.assertRaisesRegex(unittest.SkipTest, 'fragment_1.png'):
                requires_palette_fixture(root)

    def test_existing_malformed_schema_is_not_hidden(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'snapshot.json').write_text('{}')
            with self.assertRaises(KeyError):
                requires_palette_fixture(root)


if __name__ == '__main__':
    unittest.main()
