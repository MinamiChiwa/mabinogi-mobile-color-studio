import tempfile
import unittest
from unittest.mock import patch
from engine import Runner


class RunnerStrategyTests(unittest.TestCase):
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


if __name__=='__main__':unittest.main()
