import unittest,tempfile,time,os
from pathlib import Path
from unittest.mock import patch
import numpy as np
from session_store import (SessionStore,cleanup,cleanup_sessions,MARKER,
                           new_session_path,start_session_cleanup)

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

    def test_cleanup_sessions_is_age_and_size_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);now=time.time()
            for name,age in (('20260101-000000',40*86400),('20260102-000000',2*86400),
                             ('20260103-000000',60),('20260104-000000-deadbeef',40*86400)):
                folder=root/name;folder.mkdir();(folder/'capture.bin').write_bytes(b'x'*100)
                os.utime(folder,(now-age,now-age))
            (root/'notes').mkdir();(root/'notes'/'keep.txt').write_text('keep')
            result=cleanup_sessions(root,now,keep_days=30,keep_count=1,max_bytes=150)
            self.assertGreaterEqual(result['removed'],1)
            self.assertTrue((root/'notes'/'keep.txt').exists())
            self.assertTrue((root/'20260103-000000').exists())
            self.assertFalse((root/'20260104-000000-deadbeef').exists())

    def test_session_paths_are_unique_for_same_second(self):
        from datetime import datetime
        with tempfile.TemporaryDirectory() as tmp:
            now=datetime(2026,9,28,12,34,56)
            first=new_session_path(tmp,now);second=new_session_path(tmp,now)
            self.assertNotEqual(first,second)
            self.assertRegex(first.name,r'^20260928-123456-[0-9a-f]{8}$')

    def test_session_cleanup_runs_on_background_thread(self):
        import threading
        entered=threading.Event();release=threading.Event()
        def slow_cleanup(_root):entered.set();release.wait(2)
        with patch('session_store.cleanup_sessions',side_effect=slow_cleanup):
            worker=start_session_cleanup('unused')
            self.assertTrue(entered.wait(1))
            self.assertTrue(worker.is_alive())
            release.set();worker.join(1)
        self.assertFalse(worker.is_alive())
