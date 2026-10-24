import unittest,tempfile,time,os
from pathlib import Path
from unittest.mock import patch
import numpy as np
from session_store import (SessionStore,cleanup,cleanup_sessions,MARKER,
                           SESSION_MARKER,ACTIVE_MARKER,new_session_path,
                           start_session_cleanup,mark_session)

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
            self.assertFalse((folder/ACTIVE_MARKER).exists())
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
                (folder/MARKER).write_text('diagnostic')
                os.utime(folder,(now-age,now-age))
                os.utime(folder/'capture.bin',(now-age,now-age))
                os.utime(folder/MARKER,(now-age,now-age))
            (root/'notes').mkdir();(root/'notes'/'keep.txt').write_text('keep')
            result=cleanup_sessions(root,now,keep_days=30,keep_count=1,max_bytes=150)
            self.assertGreaterEqual(result['removed'],1)
            self.assertTrue((root/'notes'/'keep.txt').exists())
            self.assertTrue((root/'20260103-000000').exists())
            self.assertFalse((root/'20260104-000000-deadbeef').exists())

    def test_cleanup_uses_latest_file_and_active_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);now=time.time()
            folder=root/'20260101-000000';folder.mkdir()
            payload=folder/'log.json';payload.write_text('live')
            (folder/MARKER).write_text('diagnostic')
            old=now-40*86400
            os.utime(folder,(old,old));os.utime(payload,(now-30,now-30))
            os.utime(folder/MARKER,(old,old))
            active=folder/ACTIVE_MARKER;active.write_text('active')
            os.utime(active,(now-30,now-30))
            os.utime(folder,(old,old))
            result=cleanup_sessions(root,now,keep_days=30,keep_count=0,max_bytes=1)
            self.assertEqual(result['removed'],0)
            self.assertTrue(folder.exists())
            os.utime(active,(now-600,now-600))
            os.utime(payload,(now-600,now-600))
            os.utime(folder,(now-600,now-600))
            result=cleanup_sessions(root,now,keep_days=30,keep_count=0,max_bytes=1)
            self.assertEqual(result['removed'],1)

    def test_size_threshold_preserves_retained_recent_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);now=time.time()
            names=('20260101-000000','20260102-000000','20260103-000000')
            for index,name in enumerate(names):
                folder=root/name;folder.mkdir()
                payload=folder/'capture.bin';payload.write_bytes(b'x'*100)
                (folder/MARKER).write_text('diagnostic')
                stamp=now-(index+1)*86400
                os.utime(folder,(stamp,stamp));os.utime(payload,(stamp,stamp))
                os.utime(folder/MARKER,(stamp,stamp))
            # The byte threshold removes the oldest session first, but the
            # retained recent history is not sacrificed just to reach it.
            result=cleanup_sessions(root,now,keep_days=30,keep_count=2,max_bytes=100)
            self.assertEqual(result['removed'],1)
            self.assertTrue((root/names[0]).exists())
            self.assertTrue((root/names[1]).exists())
            self.assertFalse((root/names[2]).exists())

    def test_size_budget_keeps_active_session_even_when_over_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);now=time.time()
            folder=root/'20260101-000000';folder.mkdir()
            (folder/'capture.bin').write_bytes(b'x'*100)
            (folder/MARKER).write_text('diagnostic')
            active=folder/ACTIVE_MARKER;active.write_text('active')
            os.utime(folder,(now,now));os.utime(active,(now,now))
            result=cleanup_sessions(root,now,keep_count=0,max_bytes=1)
            self.assertEqual(result['removed'],0)
            self.assertTrue(folder.exists())

    def test_default_history_keeps_only_three_completed_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);now=time.time()
            names=[f'2026010{i}-000000' for i in range(1,6)]
            # Newer names have newer mtimes; all are safely completed.
            for index,name in enumerate(names):
                folder=root/name;folder.mkdir()
                payload=folder/'capture.bin';payload.write_bytes(b'x')
                (folder/MARKER).write_text('diagnostic')
                stamp=now-(len(names)-index)*86400
                os.utime(folder,(stamp,stamp));os.utime(payload,(stamp,stamp))
                os.utime(folder/MARKER,(stamp,stamp))
            cleanup_sessions(root,now)
            self.assertEqual(sum((root/name).exists() for name in names),3)
            self.assertTrue((root/names[-1]).exists())
            self.assertTrue((root/names[-2]).exists())
            self.assertTrue((root/names[-3]).exists())

    def test_cleanup_sessions_ignores_unmarked_timestamp_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);now=time.time()
            folder=root/'20260101-000000';folder.mkdir()
            (folder/'user-data.txt').write_text('keep')
            old=now-90*86400
            os.utime(folder,(old,old));os.utime(folder/'user-data.txt',(old,old))
            result=cleanup_sessions(root,now,keep_count=0,max_bytes=1)
            self.assertEqual(result['removed'],0)
            self.assertTrue((folder/'user-data.txt').exists())

    def test_active_owned_session_does_not_consume_completed_history_slot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);now=time.time()
            names=[f'2026010{i}-000000' for i in range(1,5)]
            for index,name in enumerate(names):
                folder=root/name
                self.assertTrue(mark_session(folder))
                (folder/'capture.bin').write_bytes(b'x')
                stamp=now-(5-index)*86400
                for path in folder.iterdir():os.utime(path,(stamp,stamp))
                os.utime(folder,(stamp,stamp))
            active=root/'20260105-000000'
            mark_session(active)
            (active/ACTIVE_MARKER).write_text('active')
            cleanup_sessions(root,now)
            self.assertFalse((root/names[0]).exists())
            self.assertTrue(all((root/name).exists() for name in names[1:]))
            self.assertTrue(active.exists())

    def test_default_history_does_not_delete_large_recent_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);now=time.time()
            names=[f'2026010{i}-000000' for i in range(1,5)]
            for index,name in enumerate(names):
                folder=root/name;folder.mkdir()
                payload=folder/'capture.bin';payload.write_bytes(b'x'*1024*1024)
                (folder/MARKER).write_text('diagnostic')
                stamp=now-(len(names)-index)*86400
                os.utime(folder,(stamp,stamp));os.utime(payload,(stamp,stamp))
                os.utime(folder/MARKER,(stamp,stamp))
            cleanup_sessions(root,now)
            self.assertEqual(sum((root/name).exists() for name in names),3)
            # The newest retained records are not evicted to meet a byte cap.
            for name in names[-3:]:self.assertEqual((root/name/'capture.bin').stat().st_size,1024*1024)

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
