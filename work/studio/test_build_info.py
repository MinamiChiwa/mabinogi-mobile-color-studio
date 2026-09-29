import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import build_info


class BuildIdentityTests(unittest.TestCase):
    def test_identity_tracks_code_but_excludes_personal_and_test_data(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            source=root/'example.py';source.write_text('value = 1',encoding='utf-8')
            before=build_info.source_identity(root)
            (root/'profile.json').write_text('{"private":true}',encoding='utf-8')
            (root/'test_example.py').write_text('test = 1',encoding='utf-8')
            self.assertEqual(before,build_info.source_identity(root))
            source.write_text('value = 2',encoding='utf-8')
            self.assertNotEqual(before['source_sha256'],build_info.source_identity(root)['source_sha256'])
            self.assertNotIn(folder,json.dumps(before))

    def test_frozen_app_uses_bundled_identity_without_source_access(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest=dict(app_version=build_info.APP_VERSION,policy_revision=build_info.POLICY_REVISION,
                          source_sha256='saved-build',git_commit='base-commit',private='excluded')
            (Path(folder)/'build-info.json').write_text(json.dumps(manifest),encoding='utf-8')
            build_info.runtime_identity.cache_clear()
            try:
                with patch.object(build_info.sys,'frozen',True,create=True), \
                     patch.object(build_info.sys,'_MEIPASS',folder,create=True), \
                     patch.object(build_info,'source_identity',side_effect=AssertionError('source access')):
                    result=build_info.runtime_identity()
                self.assertEqual(result['source_sha256'],'saved-build')
                self.assertNotIn('private',result)
            finally:build_info.runtime_identity.cache_clear()


if __name__=='__main__':unittest.main()
