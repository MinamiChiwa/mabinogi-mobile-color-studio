import hashlib
import tempfile
import unittest
from pathlib import Path

from updater.planner import plan_update
from updater.types import FileEntry,Manifest


def entry(path,content,blob='blob'):
    digest=hashlib.sha256(content).hexdigest()
    return FileEntry(path,digest,len(content),blob,hashlib.sha256(blob.encode()).hexdigest(),len(content))


class UpdatePlanTests(unittest.TestCase):
    def test_old_modified_file_is_never_scheduled_for_removal(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'_internal').mkdir();(root/'_internal/obsolete.dll').write_bytes(b'user edit')
            old=Manifest.for_test('0.4.1',(entry('_internal/obsolete.dll',b'original'),))
            new=Manifest.for_test('0.4.2',())
            plan=plan_update(root,old,new)
            self.assertNotIn('_internal/obsolete.dll',plan.removals)
            self.assertIn('_internal/obsolete.dll',plan.conflicts)

    def test_same_hash_is_reused_and_new_file_is_install(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'_internal').mkdir();(root/'_internal/same.dll').write_bytes(b'same')
            old=Manifest.for_test('0.4.1',(entry('_internal/same.dll',b'same'),))
            new=Manifest.for_test('0.4.2',(entry('_internal/same.dll',b'same'),entry('_internal/new.dll',b'new')))
            plan=plan_update(root,old,new)
            self.assertEqual(plan.reused,('_internal/same.dll',))
            self.assertEqual(plan.installs,('_internal/new.dll',))
            self.assertEqual(plan.removals,())

    def test_data_tree_is_protected_even_when_unknown_to_old_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'_internal').mkdir();(root/'data').mkdir();(root/'data'/'history.json').write_text('keep')
            old=Manifest.for_test('0.4.1',())
            new=Manifest.for_test('0.4.2',())
            plan=plan_update(root,old,new)
            self.assertIn('data',plan.protected_paths)
            self.assertEqual(plan.removals,())


if __name__=='__main__':unittest.main()
