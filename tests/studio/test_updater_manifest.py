import base64
import json
import unittest
from unittest.mock import patch

from updater.manifest import ManifestError, verify_manifest


class ManifestTests(unittest.TestCase):
    # RFC 8032 test vector 1 verifies our crypto-library boundary.
    public_key=bytes.fromhex('d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a')
    message=b''
    signature=bytes.fromhex(
        'e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155'
        '5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b')

    def test_rfc_ed25519_signature_is_accepted_and_tampering_is_rejected(self):
        from updater.manifest import verify_ed25519
        self.assertTrue(verify_ed25519(self.message,self.signature,self.public_key))
        self.assertFalse(verify_ed25519(b'3',self.signature,self.public_key))

    def test_manifest_rejects_traversal_aliases_and_data_targets(self):
        from _updater_test_support import signed,entry,KEYS
        for path in ('../evil.dll','..\\evil.dll','C:/evil.dll','\\\\server\\share\\evil.dll','data/history.json'):
            raw,sig=signed([entry(path)])
            with self.subTest(path=path):
                with self.assertRaises(ManifestError):verify_manifest(raw,sig,KEYS)

    def test_valid_manifest_is_frozen_and_versioned(self):
        from _updater_test_support import signed,entry,KEYS
        raw,sig=signed([entry()],version='0.4.2')
        manifest=verify_manifest(raw,sig,KEYS)
        self.assertEqual(manifest.version,'0.4.2')
        self.assertIsInstance(manifest.files,tuple)
        self.assertEqual(manifest.files[0].path,'ColorStudio.exe')

    def test_signed_windows_aliases_and_file_directory_conflicts_are_rejected(self):
        from _updater_test_support import signed,entry,KEYS
        cases=([entry('_internal//a.dll')],[entry('_internal/./a.dll')],
               [entry('_internal/a.dll'),entry('_internal/a.dll/b')],
               [entry('user-notes.txt')],[entry('data')])
        for rows in cases:
            with self.subTest(rows=rows),self.assertRaises(ManifestError):
                raw,sig=signed(rows);verify_manifest(raw,sig,KEYS)

    def _raw(self,files):
        return bytes(json.dumps({'schema':1,'app_id':'MabinogiMobileColorStudio','version':'0.4.2',
            'channel':'stable','platform':'win32','architecture':'x86_64','release_sequence':2,
            'minimum_updater':1,'data_schema_read':[1],'data_schema_write':1,'key_id':'test',
            'files':files},sort_keys=True,separators=(',',':')).encode())


if __name__=='__main__':unittest.main()
