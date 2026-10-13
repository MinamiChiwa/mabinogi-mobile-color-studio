import tempfile,threading,time
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from engine import Runner


class RunnerStrategyTests(unittest.TestCase):
    def test_legacy_finalize_is_disabled_before_any_game_input(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as folder:
            runner=Runner(lambda *a:None,folder);game=Mock()
            for name,args in [('submit',(game,None,[])),('apply_result',(game,None,[])),('reject',(game,None))]:
                with self.subTest(name=name),self.assertRaisesRegex(RuntimeError,'手动'):
                    getattr(runner,name)(*args)
            game.click.assert_not_called();game.capture.assert_not_called()

    def test_screenshot_canonical_name_and_auto_apply_are_enforced(self):
        from unittest.mock import Mock,patch
        with tempfile.TemporaryDirectory() as folder:
            service=Mock(return_value='done');runner=Runner(lambda *a:None,folder,atlas_runner=service)
            with patch('engine.configure_ocr'):
                self.assertEqual(runner.launch([],strategy='screenshot',auto=True),'done')
            self.assertFalse(service.call_args.kwargs['auto'])

    def test_slow_stop_saves_worker_stack_without_claiming_worker_has_finished(self):
        events=[];started=threading.Event();unblock=threading.Event()
        def delayed(owner,*args,**kwargs):
            owner.event('native_progress',stage='native_validate',message='Fixture')
            started.set();unblock.wait(5)
        with tempfile.TemporaryDirectory() as tmp:
            runner=Runner(lambda kind,data:events.append((kind,data)),tmp,native_runner=delayed)
            self.assertTrue(callable(getattr(runner,'request_stop',None)),'Stop receipt/slow-worker evidence is missing')
            with patch('engine.start_session_cleanup'):
                thread=threading.Thread(target=lambda:runner.launch([],strategy='native'));thread.start()
                try:
                    self.assertTrue(started.wait(1));runner.request_stop('hotkey_message')
                    evidence=Path(tmp)/'stop-wait.json';end=time.monotonic()+3
                    while not evidence.exists() and time.monotonic()<end:time.sleep(.025)
                    self.assertTrue(evidence.is_file(),'A worker that ignored F9 left no diagnostic')
                    record=json.loads(evidence.read_text(encoding='utf-8'))
                    self.assertEqual(record['stop_diagnostic']['source'],'hotkey_message')
                    self.assertEqual(record['last_event']['stage'],'native_validate')
                    self.assertIn('delayed',''.join(record['worker_stack']))
                    self.assertTrue(thread.is_alive());self.assertFalse(any(kind=='finished' for kind,data in events))
                finally:unblock.set();thread.join(2)
            self.assertEqual(sum(kind=='finished' for kind,data in events),1)

    def test_startup_file_error_still_releases_busy_ui_with_one_terminal_event(self):
        events=[]
        with tempfile.TemporaryDirectory() as tmp:
            runner=Runner(lambda kind,data:events.append((kind,data)),tmp,native_runner=lambda *args,**kwargs:None)
            original=Path.write_text
            def write(path,*args,**kwargs):
                if path.name=='.color-studio-active':raise OSError('Fixture startup file failure')
                return original(path,*args,**kwargs)
            with patch.object(Path,'write_text',new=write):
                try:runner.launch([],strategy='native')
                except OSError:pass
        self.assertEqual(sum(kind=='finished' for kind,data in events),1,'Early worker failure left the UI busy forever')

    def test_event_evidence_is_available_before_the_worker_finishes(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner=Runner(lambda *_:None,tmp)
            runner.event('window_bound',hwnd=1,pid=2,title='Fixture')
            evidence=Path(tmp)/'run-events.jsonl'
            self.assertTrue(evidence.is_file(),'A hung startup must not leave only session markers')
            first=json.loads(evidence.read_text(encoding='utf-8').splitlines()[0])
            self.assertEqual(first['kind'],'window_bound');self.assertEqual(first['pid'],2)
            runner.event('native_progress',stage='native_validate',message='Fixture')
            self.assertEqual(len(evidence.read_text(encoding='utf-8').splitlines()),2)

    def test_stopped_run_summary_keeps_first_source_for_native_and_screenshot_paths(self):
        def stopped(owner,rules,**kwargs):
            owner.stop.request('hotkey_message');owner.stop.set()
        for strategy in ('native','atlas'):
            with self.subTest(strategy=strategy),tempfile.TemporaryDirectory() as tmp:
                folder=Path(tmp)/'20261013-120000-12345678'
                runner=Runner(lambda *_:None,folder,native_runner=stopped,screenshot_runner=stopped)
                with patch('engine.configure_ocr'),patch('engine.start_session_cleanup'):
                    runner.launch([],strategy=strategy)
                summary=json.loads((folder/'run-summary.json').read_text(encoding='utf-8'))
                self.assertTrue(summary['stop_requested'])
                self.assertEqual(summary.get('stop_diagnostic',{}).get('source'),'hotkey_message')

    def test_normal_atlas_root_is_owned_and_cleaned_after_completion(self):
        from session_store import SESSION_MARKER,ACTIVE_MARKER
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'20261002-120000-12345678'
            def atlas(owner,rules,**kwargs):
                self.assertTrue((folder/SESSION_MARKER).is_file())
                self.assertTrue((folder/ACTIVE_MARKER).is_file())
                return 'done'
            runner=Runner(lambda *_:None,folder,atlas_runner=atlas)
            with patch('engine.configure_ocr'),patch('engine.start_session_cleanup') as clean:
                self.assertEqual(runner.launch([],strategy='atlas'),'done')
            self.assertTrue((folder/SESSION_MARKER).is_file())
            self.assertFalse((folder/ACTIVE_MARKER).exists())
            clean.assert_called_once_with(folder.parent)

    def test_atlas_strategy_uses_injected_runner_without_touching_legacy(self):
        seen=[]
        def atlas(owner,rules,**kwargs):
            seen.append((owner,rules,kwargs));return 'atlas-result'
        with tempfile.TemporaryDirectory() as folder:
            runner=Runner(lambda *_:None,folder,atlas_runner=atlas)
            with patch('engine.configure_ocr') as configure:
                self.assertEqual(runner.launch([],strategy='atlas',mode='search'), 'atlas-result')
            configure.assert_called_once_with()
        self.assertEqual(seen[0][1],[])
        self.assertEqual(seen[0][2]['mode'],'search')

    def test_atlas_strategy_fails_closed_when_not_connected(self):
        with tempfile.TemporaryDirectory() as folder:
            runner=Runner(lambda *_:None,folder)
            with self.assertRaisesRegex(RuntimeError,'not connected'):
                runner.launch([],strategy='atlas')

    def test_only_single_enabled_search_uses_direct_board_branch(self):
        from unittest.mock import Mock
        for enabled in ((True,False,False),(False,True,False),(False,False,True),
                        (True,True,False),(True,True,True)):
            rules=[dict(enabled=value,colors=['#000000'],exact=True,tolerance=8) for value in enabled]
            events=[];atlas=Mock(return_value='atlas')
            with tempfile.TemporaryDirectory() as folder:
                runner=Runner(lambda k,d:events.append((k,d)),folder,atlas_runner=atlas)
                with patch('engine.configure_ocr'),patch('single_region_live.run_live_single_region',return_value='direct') as direct:
                    result=runner.launch(rules,strategy='atlas',mode='search',target='selected')
                if sum(enabled)==1:
                    self.assertEqual(result,'direct');atlas.assert_not_called()
                    self.assertEqual(direct.call_args.kwargs['target'],'selected')
                else:
                    self.assertEqual(result,'atlas');direct.assert_not_called()
                self.assertEqual(events[-1][0],'finished')

    def test_single_branch_f9_finishes_without_atlas_recovery(self):
        from platform_win import Interrupted
        rules=[dict(enabled=i==0,colors=['#000000'],exact=True,tolerance=8) for i in range(3)]
        events=[]
        with tempfile.TemporaryDirectory() as folder:
            runner=Runner(lambda k,d:events.append((k,d)),folder)
            with patch('engine.configure_ocr'),patch('single_region_live.run_live_single_region',side_effect=Interrupted('F9')):
                runner.launch(rules,strategy='atlas',mode='search')
        self.assertEqual([k for k,d in events],['config','interrupted','finished'])


if __name__=='__main__':unittest.main()
