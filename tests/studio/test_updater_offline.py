import io,warnings
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from updater.offline import import_offline,OfflinePackageError


class OfflineTests(unittest.TestCase):
    def test_zip_slip_and_duplicate_members_are_rejected_before_extraction(self):
        with tempfile.TemporaryDirectory() as temp:
            archive=Path(temp)/'bad.zip';cache=Path(temp)/'cache'
            with warnings.catch_warnings():
                warnings.simplefilter('ignore',UserWarning)
                with zipfile.ZipFile(archive,'w') as z:
                    z.writestr('../evil','x');z.writestr('../evil','y')
            with self.assertRaises(OfflinePackageError):import_offline(archive,cache,{},trusted_keys={})
            self.assertFalse((Path(temp)/'evil').exists())

    def test_missing_signature_is_rejected_without_creating_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            archive=Path(temp)/'bad.zip'
            with zipfile.ZipFile(archive,'w') as z:z.writestr('update-manifest.json',b'{}')
            with self.assertRaises(OfflinePackageError):import_offline(archive,Path(temp)/'cache',{},trusted_keys={})


if __name__=='__main__':unittest.main()
