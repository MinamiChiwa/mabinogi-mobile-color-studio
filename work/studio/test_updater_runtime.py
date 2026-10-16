import json,tempfile,time,unittest,zipfile
from pathlib import Path
from _updater_test_support import SEED,KEYS
from scripts.build_update_assets import build_assets

class RuntimeTests(unittest.TestCase):
    def wait(self,runtime):
        runtime.worker.join(10);self.assertFalse(runtime.worker.is_alive())
    def test_rate_limited_discovery_survives_restart_without_downloading_or_installing(self):
        from updater.runtime import UpdateRuntime
        from updater.discovery import API,BASE
        from test_updater_network import Response
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'app';root.mkdir();(root/'ColorStudio.exe').write_bytes(b'old')
            old=Path(temp)/'old';build_assets(root,old,'0.4.2','stable',SEED)
            for name in ('update-manifest.json','update-manifest.sig'):(root/name).write_bytes((old/name).read_bytes())
            new=Path(temp)/'new';(root/'ColorStudio.exe').write_bytes(b'new')
            build_assets(root,new,'0.4.3','stable',SEED,release_sequence=2)
            (root/'ColorStudio.exe').write_bytes(b'old')
            data=root/'data';data.mkdir();(data/'profile.json').write_bytes(b'private')
            calls=[];latest=BASE+'/releases/latest/download/'
            class Fixture:
                def get(self,url,headers=None,timeout=None):
                    calls.append(url)
                    if url==API+'/latest':return Response(429,b'{}',{'Retry-After':'3600'})
                    assert url in (latest+'update-manifest.json',latest+'update-manifest.sig')
                    return Response(200,(new/url.rsplit('/',1)[1]).read_bytes())
            for _ in range(2):
                events=[];runtime=UpdateRuntime(root,data,'0.4.2',events.append,keys=KEYS,client=Fixture())
                runtime.check(manual=True);self.wait(runtime)
                self.assertEqual(runtime.service.state,'available',events)
                self.assertEqual(runtime.service.manifest.version,'0.4.3')
                self.assertFalse(runtime.cache.exists())
                self.assertFalse((root/'.colorstudio-pending.json').exists())
            self.assertEqual(calls.count(API+'/latest'),0)
            self.assertEqual((root/'ColorStudio.exe').read_bytes(),b'old')
            self.assertEqual((data/'profile.json').read_bytes(),b'private')
    def test_check_does_not_download_and_offline_ready_keeps_user_data(self):
        from updater.runtime import UpdateRuntime
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'工具';root.mkdir();(root/'ColorStudio.exe').write_bytes(b'old')
            old=Path(temp)/'old';old_report=build_assets(root,old,'0.4.2','stable',SEED)
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
            old=Path(temp)/'old';old_report=build_assets(root,old,'0.4.2','stable',SEED)
            for name in ('update-manifest.json','update-manifest.sig'):(root/name).write_bytes((old/name).read_bytes())
            data=root/'data';data.mkdir();new=Path(temp)/'new'
            (root/'ColorStudio.exe').write_bytes(b'new');good=build_assets(root,new,'0.4.3','stable',SEED,release_sequence=2)
            (root/'ColorStudio.exe').write_bytes(b'old')
            events=[];runtime=UpdateRuntime(root,data,'0.4.2',events.append,keys=KEYS)
            runtime.offline(new/good['offline_name']);self.wait(runtime)
            before=(runtime.cache/'update-manifest.json').read_bytes()
            self.assertTrue((old/old_report['offline_name']).is_file())
            runtime.offline(old/old_report['offline_name']);self.wait(runtime)
            self.assertEqual(runtime.service.state,'ready')
            self.assertEqual((runtime.cache/'update-manifest.json').read_bytes(),before)
