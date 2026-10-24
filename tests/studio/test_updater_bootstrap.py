from test_paths import STUDIO
import json,tempfile,unittest
from pathlib import Path

class BootstrapTests(unittest.TestCase):
    def test_ready_process_can_detect_a_dead_or_recycled_helper(self):
        from update_bootstrap import helper_alive
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            tx=Path(temp);(tx/'helper-owner.json').write_text(json.dumps({'pid':123,'creation':456}))
            with patch('updater.win_process.process_creation',return_value=456):self.assertTrue(helper_alive(tx))
            with patch('updater.win_process.process_creation',return_value=789):self.assertFalse(helper_alive(tx))
            with patch('updater.win_process.process_creation',return_value=None):self.assertFalse(helper_alive(tx))

    def test_bootstrap_recovery_refuses_replaced_external_helper(self):
        from update_bootstrap import dispatch
        from _updater_test_support import signed,entry,KEYS
        from unittest.mock import patch
        import hashlib
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'app';root.mkdir();tx=Path(temp)/'tx';tx.mkdir()
            raw,sig=signed([entry('ColorStudioUpdater.exe',sha256=hashlib.sha256(b'good').hexdigest(),size=4)])
            (tx/'old-manifest.json').write_bytes(raw);(tx/'old-manifest.sig').write_bytes(sig)
            (tx/'ColorStudioUpdater.exe').write_bytes(b'bad')
            (root/'.colorstudio-pending.json').write_text(json.dumps({'transaction':str(tx)}))
            (tx/'transaction.json').write_text(json.dumps({'root':str(root)}));(tx/'state.json').write_text(json.dumps({'status':'applying'}))
            with patch('update_bootstrap.installation_root',return_value=root),patch('update_recovery_identity.HELPER_SHA256',hashlib.sha256(b'good').hexdigest()),patch('update_bootstrap.subprocess.Popen') as launch:
                with self.assertRaises(RuntimeError):dispatch([])
                launch.assert_not_called()

    def test_recovery_launch_needs_no_replaceable_crypto_and_uses_matching_helper(self):
        from update_bootstrap import dispatch
        from unittest.mock import patch
        import hashlib,builtins
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'app';root.mkdir();tx=Path(temp)/'tx';tx.mkdir()
            (root/'.colorstudio-pending.json').write_text(json.dumps({'transaction':str(tx)}))
            (tx/'transaction.json').write_text(json.dumps({'root':str(root)}));(tx/'state.json').write_text(json.dumps({'status':'applying'}))
            (tx/'ColorStudioUpdater.exe').write_bytes(b'old');(tx/'target-helper.exe').write_bytes(b'new')
            original=builtins.__import__
            def guarded(name,*args,**kwargs):
                if name.startswith(('updater','cryptography','packaging')):raise ImportError('half-replaced dependency')
                return original(name,*args,**kwargs)
            with patch('update_bootstrap.installation_root',return_value=root),patch('update_recovery_identity.HELPER_SHA256',hashlib.sha256(b'new').hexdigest()),\
                    patch('builtins.__import__',side_effect=guarded),patch('update_bootstrap.subprocess.Popen') as launch:
                self.assertEqual(dispatch([]),0)
                self.assertEqual(launch.call_args.args[0][0],str(tx/'target-helper.exe'))

    def test_fresh_process_recovers_without_importing_any_updater_dependency(self):
        import subprocess,sys,hashlib,os
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'app';root.mkdir();tx=Path(temp)/'tx';tx.mkdir()
            (root/'.colorstudio-pending.json').write_text(json.dumps({'transaction':str(tx)}))
            (tx/'transaction.json').write_text(json.dumps({'root':str(root)}));(tx/'state.json').write_text(json.dumps({'status':'applying'}))
            (tx/'target-helper.exe').write_bytes(b'new')
            script='''import builtins,sys
original=builtins.__import__
def guarded(name,*args,**kwargs):
    if name.startswith(('updater','cryptography','packaging')):raise ImportError('half-replaced dependency')
    return original(name,*args,**kwargs)
builtins.__import__=guarded
import update_bootstrap as bootstrap
import update_recovery_identity as embedded
from pathlib import Path
embedded.HELPER_SHA256=sys.argv[2]
bootstrap.installation_root=lambda:Path(sys.argv[1])
calls=[]
bootstrap.subprocess.Popen=lambda *args,**kwargs:calls.append(args[0])
assert bootstrap.dispatch([])==0
assert calls[0][0].endswith('target-helper.exe')
'''
            env=dict(os.environ,PYTHONPATH=str(STUDIO))
            result=subprocess.run([sys.executable,'-c',script,str(root),hashlib.sha256(b'new').hexdigest()],env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
    def test_pending_transaction_blocks_normal_launch_until_recovered(self):
        from update_bootstrap import pending_transaction
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'app';root.mkdir();tx=Path(temp)/'tx';tx.mkdir()
            (root/'.colorstudio-pending.json').write_text(json.dumps({'transaction':str(tx)}))
            (tx/'transaction.json').write_text(json.dumps({'root':str(root)}))
            (tx/'state.json').write_text(json.dumps({'status':'applying'}))
            self.assertEqual(pending_transaction(root),tx)
            (tx/'state.json').write_text(json.dumps({'status':'committed'}))
            self.assertIsNone(pending_transaction(root))

    def test_requested_data_directory_is_used_without_migration(self):
        from update_bootstrap import active_data_directory
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'app';root.mkdir();data=Path(temp)/'用户资料';data.mkdir()
            (root/'update-location.json').write_text(json.dumps({'data':str(data),'schema':1}))
            self.assertEqual(active_data_directory(root),data)
