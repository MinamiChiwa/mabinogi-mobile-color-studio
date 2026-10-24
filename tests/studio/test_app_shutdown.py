"""Startup/close event races in a fresh Tk process, with no game or hotkeys."""
from test_paths import STUDIO
import os,subprocess,sys,unittest
from pathlib import Path

class ShutdownTests(unittest.TestCase):
    def test_f9_from_background_message_finishes_and_same_ui_can_start_again(self):
        script='''import json,queue,tempfile,threading
from pathlib import Path
from unittest.mock import patch
import app
from engine import Runner
feed=queue.Queue();trigger=threading.Event();closing=threading.Event();count=[0];errors=[]
def hotkeys(*args):
    feed.put(args[4])
    for _ in range(2):
        if not trigger.wait(5):return
        trigger.clear();args[4]('hotkey',dict(id=2,source='message'))
    closing.wait(5)
def service(owner,*args,**kwargs):
    if not owner.stop.wait(5):raise RuntimeError('No stop request')
    raise InterruptedError('Stopped fixture')
def build(emit,folder,strategy):return Runner(emit,folder,native_runner=service)
with tempfile.TemporaryDirectory() as temp,patch.object(app,'DATA',Path(temp)),patch.object(app,'run_hotkeys',side_effect=hotkeys),patch.object(app,'build_runner',side_effect=build):
    ui=app.App();ui.search_strategy.set('native');ui.updater.check=lambda *args:None
    ui.report_callback_exception=lambda *exc:errors.append(str(exc[1]));feed.get(timeout=3)
    def completed():
        if ui.busy:ui.after(50,completed);return
        assert ui.runner is None and ui.start.cget('state')=='normal'
        assert ui.overlay._dismissed
        count[0]+=1
        if count[0]<2:ui.after(100,start);return
        summaries=list((Path(temp)/'sessions').glob('*/run-summary.json'));assert len(summaries)==2
        assert all(json.loads(path.read_text(encoding='utf-8'))['stop_diagnostic']['source']=='hotkey_message' for path in summaries)
        assert not errors,errors
        print('Two F9 stops returned controls and preserved next-run UI',flush=True)
        closing.set();ui.close()
    def start():
        ui.go();ui.after(150,lambda:(trigger.set(),ui.after(50,completed)))
    ui.after(100,start);ui.mainloop()
'''
        result=subprocess.run([sys.executable,'-c',script],env=dict(os.environ,PYTHONPATH=str(STUDIO)),capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('Two F9 stops returned controls',result.stdout)
        self.assertNotIn('invalid command name',result.stderr)

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
        result=subprocess.run([sys.executable,'-c',script],env=dict(os.environ,PYTHONPATH=str(STUDIO)),capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertNotIn('application has been destroyed',result.stderr)
        self.assertNotIn('invalid command name',result.stderr)
