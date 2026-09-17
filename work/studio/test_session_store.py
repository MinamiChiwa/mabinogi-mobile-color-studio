import unittest,tempfile,time,os
from pathlib import Path
import numpy as np
from session_store import SessionStore,cleanup,MARKER

class SessionStoreTests(unittest.TestCase):
    def test_normal_run_creates_no_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'sessions'/'run'
            store=SessionStore(folder)
            store.image('step',np.zeros((20,20,3),np.uint8));store.event({'kind':'test'});store.close()
            self.assertFalse(folder.exists())
    def test_diagnostic_writes_and_closes(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'run';store=SessionStore(folder,True)
            store.image('step',np.zeros((20,20,3),np.uint8));store.event({'kind':'test'});store.close()
            self.assertTrue((folder/'step.png').is_file())
            self.assertTrue((folder/'events.jsonl').is_file())
    def test_cleanup_preserves_unmarked_user_files_and_active_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);now=time.time()
            for name in ('expired','old','active','user'):
                folder=root/name;folder.mkdir();(folder/'step.png').write_bytes(b'x'*100)
                if name!='user':
                    marker=folder/MARKER;marker.touch()
                    stamp=now-8*86400 if name=='expired' else now-600 if name=='old' else now
                    os.utime(marker,(stamp,stamp))
            (root/'expired'/'profile.json').write_text('{}')
            cleanup(root,now,limit=150)
            self.assertFalse((root/'expired'/'step.png').exists())
            self.assertFalse((root/'old'/'step.png').exists())
            self.assertTrue((root/'expired'/'profile.json').exists())
            self.assertTrue((root/'user'/'step.png').exists())
            self.assertTrue((root/'active'/'step.png').exists())
