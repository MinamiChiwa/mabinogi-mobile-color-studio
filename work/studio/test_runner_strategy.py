import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from engine import Runner


class RunnerStrategyTests(unittest.TestCase):
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
