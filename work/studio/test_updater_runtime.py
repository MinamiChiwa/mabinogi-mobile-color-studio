import json,tempfile,time,unittest,zipfile
from pathlib import Path
from _updater_test_support import SEED,KEYS
from scripts.build_update_assets import build_assets

class RuntimeTests(unittest.TestCase):
    def wait(self,runtime):
        runtime.worker.join(10);self.assertFalse(runtime.worker.is_alive())
    def test_check_does_not_download_and_offline_ready_keeps_user_data(self):
        from updater.runtime import UpdateRuntime
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'工具';root.mkdir();(root/'ColorStudio.exe').write_bytes(b'old')
            old=Path(temp)/'old';build_assets(root,old,'0.4.2','stable',SEED)
            for name in ('update-manifest.json','update-manifest.sig'):(root/name).write_bytes((old/name).read_bytes())
            data=root/'data';data.mkdir();(data/'profile.json').write_bytes(b'private')
            new=Path(temp)/'new';(root/'ColorStudio.exe').write_bytes(b'new')
            report=build_assets(root,new,'0.4.3','stable',SEED,release_sequence=2)
            (root/'ColorStudio.exe').write_bytes(b'old')
            events=[];runtime=UpdateRuntime(root,data,'0.4.2',events.append,keys=KEYS)
            runtime.offline(new/report['offline_name']);self.wait(runtime)
            self.assertEqual(runtime.service.state,'ready',events)
            self.assertEqual((root/'ColorStudio.exe').read_bytes(),b'old')
            self.assertEqual((data/'profile.json').read_bytes(),b'private')
            self.assertLess(runtime.service.plan.download_bytes,1000)
            runtime.set_busy(True);runtime.install()
            self.assertFalse((root/'.colorstudio-pending.json').exists())

    def test_rejected_offline_import_keeps_previous_ready_package(self):
        from updater.runtime import UpdateRuntime
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'app';root.mkdir();(root/'ColorStudio.exe').write_bytes(b'old')
            old=Path(temp)/'old';build_assets(root,old,'0.4.2','stable',SEED)
            for name in ('update-manifest.json','update-manifest.sig'):(root/name).write_bytes((old/name).read_bytes())
            data=root/'data';data.mkdir();new=Path(temp)/'new'
            (root/'ColorStudio.exe').write_bytes(b'new');good=build_assets(root,new,'0.4.3','stable',SEED,release_sequence=2)
            (root/'ColorStudio.exe').write_bytes(b'old')
            events=[];runtime=UpdateRuntime(root,data,'0.4.2',events.append,keys=KEYS)
            runtime.offline(new/good['offline_name']);self.wait(runtime)
            before=(runtime.cache/'update-manifest.json').read_bytes()
            runtime.offline(old/'ColorStudio-offline-0.4.2-win-x64.zip');self.wait(runtime)
            self.assertEqual(runtime.service.state,'ready')
            self.assertEqual((runtime.cache/'update-manifest.json').read_bytes(),before)
