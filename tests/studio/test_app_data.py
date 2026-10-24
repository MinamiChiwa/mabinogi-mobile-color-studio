import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app_data
from app_data import APP_DATA_NAME, resolve_data_directory


class AppDataTests(unittest.TestCase):
    def test_uses_portable_directory_when_it_is_writable(self):
        with tempfile.TemporaryDirectory() as root:
            preferred = Path(root) / 'portable' / 'data'
            local = Path(root) / 'local'
            selected = resolve_data_directory(preferred, local, Path(root) / 'temp')
            self.assertEqual(selected, preferred)
            self.assertTrue(preferred.is_dir())
            self.assertEqual(list(preferred.iterdir()), [])

    def test_read_only_location_falls_back_and_preserves_small_user_data(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            preferred = root / 'portable' / 'data'
            preferred.mkdir(parents=True)
            settings = {'language': 'English'}
            (preferred / 'settings.json').write_text(json.dumps(settings), encoding='utf-8')
            (preferred / 'profile.json').write_text('[]', encoding='utf-8')
            (preferred / 'sessions').mkdir()
            (preferred / 'sessions' / 'large-capture.bin').write_bytes(b'capture')
            blocked_local = root / 'local'
            blocked_local.write_text('not a directory', encoding='utf-8')
            prepare = app_data._prepare_directory

            def deny_preferred(path):
                if Path(path) == preferred:
                    raise PermissionError('read-only')
                return prepare(path)

            with patch('app_data._prepare_directory', side_effect=deny_preferred):
                selected = resolve_data_directory(preferred, blocked_local, root / 'temp')

            self.assertEqual(selected, root / 'temp' / APP_DATA_NAME / 'data')
            self.assertEqual(json.loads((selected / 'settings.json').read_text(encoding='utf-8')),
                             settings)
            self.assertTrue((selected / 'profile.json').is_file())
            self.assertFalse((selected / 'sessions').exists())

    def test_uses_local_app_data_before_temporary_storage(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            preferred = root / 'blocked'
            preferred.write_text('not a directory', encoding='utf-8')
            selected = resolve_data_directory(preferred, root / 'local', root / 'temp')
            self.assertEqual(selected, root / 'local' / APP_DATA_NAME / 'data')
            self.assertFalse((root / 'temp' / APP_DATA_NAME).exists())


if __name__ == '__main__':
    unittest.main()
