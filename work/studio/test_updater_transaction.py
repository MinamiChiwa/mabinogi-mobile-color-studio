import hashlib,json,tempfile,unittest
from pathlib import Path

from updater.transaction import apply_update,recover_update


class TransactionTests(unittest.TestCase):
    def test_every_journal_boundary_recovers_old_program_and_unknown_files(self):
        for point in ('after_intent','after_backup','after_replace','after_done'):
            with self.subTest(point=point),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);(root/'_internal').mkdir();(root/'ColorStudio.exe').write_bytes(b'old')
                (root/'_internal/obsolete.dll').write_bytes(b'obsolete');(root/'notes.txt').write_bytes(b'user')
                staging=root/'staging';staging.mkdir();(staging/'ColorStudio.exe').write_bytes(b'new')
                tx=self._transaction(root,staging)
                with self.assertRaises(RuntimeError):apply_update(tx,fault=point)
                recover_update(tx);recover_update(tx)
                self.assertEqual((root/'ColorStudio.exe').read_bytes(),b'old')
                self.assertEqual((root/'_internal/obsolete.dll').read_bytes(),b'obsolete')
                self.assertEqual((root/'notes.txt').read_bytes(),b'user')
    def _transaction(self,root,staging):
        tx=root/'tx';tx.mkdir();backup=tx/'backup';backup.mkdir()
        payload={'schema':1,'root':str(root),'staging':str(staging),'backup':str(backup),
            'operations':[{'kind':'replace','path':'ColorStudio.exe','staged':'ColorStudio.exe'},
                          {'kind':'remove','path':'_internal/obsolete.dll'}]}
        (tx/'transaction.json').write_text(json.dumps(payload),encoding='utf-8');return tx

    def test_crash_after_backup_recovers_program_and_user_data_idempotently(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'_internal').mkdir();(root/'ColorStudio.exe').write_bytes(b'old');(root/'_internal/obsolete.dll').write_bytes(b'obsolete')
            (root/'data').mkdir();(root/'data'/'history.json').write_text('keep')
            staging=root/'staging';staging.mkdir();(staging/'ColorStudio.exe').write_bytes(b'new')
            tx=self._transaction(root,staging)
            with self.assertRaises(RuntimeError):apply_update(tx,fault='after_backup')
            recover_update(tx);recover_update(tx)
            self.assertEqual((root/'ColorStudio.exe').read_bytes(),b'old')
            self.assertEqual((root/'_internal/obsolete.dll').read_bytes(),b'obsolete')
            self.assertEqual((root/'data'/'history.json').read_text(),'keep')

    def test_commit_replaces_and_removes_only_owned_program_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'_internal').mkdir();(root/'ColorStudio.exe').write_bytes(b'old');(root/'_internal/obsolete.dll').write_bytes(b'obsolete')
            (root/'data').mkdir();(root/'data'/'x').write_text('keep')
            staging=root/'staging';staging.mkdir();(staging/'ColorStudio.exe').write_bytes(b'new')
            tx=self._transaction(root,staging);apply_update(tx)
            self.assertEqual((root/'ColorStudio.exe').read_bytes(),b'new');self.assertFalse((root/'_internal/obsolete.dll').exists())
            self.assertEqual((root/'data'/'x').read_text(),'keep')

    def test_crash_after_new_file_rename_recovers_even_before_done_log(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);staging=root/'staging';staging.mkdir()
            (staging/'ColorStudio.exe').write_bytes(b'new');tx=self._transaction(root,staging)
            with self.assertRaises(RuntimeError):apply_update(tx,fault='after_replace')
            recover_update(tx);recover_update(tx)
            self.assertFalse((root/'ColorStudio.exe').exists())

    def test_health_failure_restores_owned_files_without_touching_data(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'ColorStudio.exe').write_bytes(b'old')
            (root/'data').mkdir();(root/'data/u').write_bytes(b'keep')
            staging=root/'staging';staging.mkdir();(staging/'ColorStudio.exe').write_bytes(b'new')
            tx=self._transaction(root,staging)
            apply_update(tx,health_check=lambda:False)
            self.assertEqual((root/'ColorStudio.exe').read_bytes(),b'old')
            self.assertEqual((root/'data/u').read_bytes(),b'keep')


if __name__=='__main__':unittest.main()
