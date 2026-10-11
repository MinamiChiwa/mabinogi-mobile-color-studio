"""Real preparation and helper revalidation; no executable is launched."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from _updater_test_support import KEYS,SEED
from scripts.build_update_assets import build_assets
from updater.runtime import UpdateRuntime
from update_helper import validated_transaction

class HelperTests(unittest.TestCase):
    def test_commit_journal_failure_stops_ready_child_before_restoring_files(self):
        import update_helper as helper
        import updater.transaction as journal
        from updater.paths import atomic_json
        class Child:
            def __init__(self,exit_code=None):self.exit_code=exit_code
            def poll(self):return self.exit_code
            def wait(self,timeout=None):return self.exit_code
            def terminate(self):self.exit_code=1
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'app';root.mkdir();tx=Path(temp)/'tx';tx.mkdir();stage=root/'stage';stage.mkdir()
            (root/'ColorStudio.exe').write_bytes(b'old');(stage/'ColorStudio.exe').write_bytes(b'new')
            record=dict(schema=1,root=str(root),staging=str(stage),backup=str(root/'backup'),token='same',version='0.4.3',
                operations=[dict(kind='replace',path='ColorStudio.exe')])
            atomic_json(tx/'transaction.json',record)
            for name in ('health.json','ready.json'):atomic_json(tx/name,dict(token='same',version='0.4.3'))
            ready=Child();original_write=journal._write_state;original_recover=helper.recover_update
            def write(path,state):
                if state['status']=='committed':raise OSError('commit journal failure')
                original_write(path,state)
            def recover(path):
                self.assertIsNotNone(ready.poll(),'New readiness process must exit before old EXE restoration')
                return original_recover(path)
            with patch.object(helper,'validated_transaction',return_value=(record,root)),patch.object(helper,'other_install_instances',return_value=[]),\
                    patch.object(helper.subprocess,'Popen',side_effect=[Child(0),ready,Child()]),\
                    patch.object(journal,'_write_state',side_effect=write),patch.object(helper,'recover_update',side_effect=recover):
                with self.assertRaises(OSError):helper.run(tx,trusted_keys=KEYS)
            self.assertEqual((root/'ColorStudio.exe').read_bytes(),b'old')
    def test_helper_revalidates_prepared_files_and_rejects_tampered_operations(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'工具';root.mkdir();(root/'ColorStudio.exe').write_bytes(b'old')
            (root/'ColorStudioUpdater.exe').write_bytes(b'independent helper')
            old=Path(temp)/'old';build_assets(root,old,'0.4.2','stable',SEED)
            for name in ('update-manifest.json','update-manifest.sig'):(root/name).write_bytes((old/name).read_bytes())
            data=root/'data';data.mkdir();(data/'keep').write_bytes(b'user')
            (root/'ColorStudio.exe').write_bytes(b'new');new=Path(temp)/'new'
            report=build_assets(root,new,'0.4.3','stable',SEED,release_sequence=2)
            (root/'ColorStudio.exe').write_bytes(b'old')
            runtime=UpdateRuntime(root,data,'0.4.2',lambda e:None,keys=KEYS)
            runtime.offline(new/report['offline_name']);runtime.worker.join(10)
            self.assertEqual(runtime.service.state,'ready')
            with patch('updater.runtime.sys.frozen',True,create=True),patch('updater.runtime.launch_helper'):
                runtime.prepare_install(runtime.service.plan)
            tx=Path(json.loads((root/'.colorstudio-pending.json').read_text())['transaction'])
            self.addCleanup(__import__('shutil').rmtree,tx)
            record,selected=validated_transaction(tx,KEYS)
            self.assertEqual(selected,root);self.assertEqual((data/'keep').read_bytes(),b'user')
            record['operations'].append(dict(record['operations'][0]))
            (tx/'transaction.json').write_text(json.dumps(record))
            with self.assertRaises(ValueError):validated_transaction(tx,KEYS)
