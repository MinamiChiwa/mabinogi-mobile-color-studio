import tempfile,unittest,subprocess,sys
from pathlib import Path

class WindowsUpdateTests(unittest.TestCase):
    def test_lock_is_released_after_process_crash(self):
        from updater.win_process import UpdateLock
        with tempfile.TemporaryDirectory() as temp:
            code="from updater.win_process import UpdateLock; import os; lock=UpdateLock(r'"+temp+"'); lock.__enter__(); os._exit(1)"
            subprocess.run([sys.executable,'-c',code],check=False)
            with UpdateLock(temp):pass

    def test_active_lock_rejects_another_instance(self):
        from updater.win_process import UpdateLock
        with tempfile.TemporaryDirectory() as temp,UpdateLock(temp):
            with self.assertRaises(RuntimeError):
                with UpdateLock(temp):pass
