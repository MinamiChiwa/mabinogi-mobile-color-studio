"""Startup/close event races in a fresh Tk process, with no game or hotkeys."""
import os,subprocess,sys,unittest
from pathlib import Path

class ShutdownTests(unittest.TestCase):
    def test_queued_close_before_first_mainloop_exits_without_destroyed_wm_error(self):
        script='''import tempfile
from pathlib import Path
from unittest.mock import patch
import app
with tempfile.TemporaryDirectory() as temp,patch.object(app,'DATA',Path(temp)),patch.object(app.App,'hotkey_loop'),patch.object(app,'resolve_target',side_effect=RuntimeError('isolated')):
    ui=app.App()
    ui.after(0,ui.close)
    ui.mainloop()
'''
        result=subprocess.run([sys.executable,'-c',script],env=dict(os.environ,PYTHONPATH=str(Path(__file__).parent)),capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertNotIn('application has been destroyed',result.stderr)
        self.assertNotIn('invalid command name',result.stderr)
