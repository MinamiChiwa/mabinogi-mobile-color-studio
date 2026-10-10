"""Native dispatch owns lifecycle and never enters legacy auto-apply code."""
import inspect,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from engine import Runner


class NativeRunnerTests(unittest.TestCase):
    def test_native_strategy_runs_injected_service_and_cleans_active_marker(self):
        self.assertIn('native_runner',inspect.signature(Runner).parameters,'Native runner connection missing')
        from session_store import ACTIVE_MARKER,SESSION_MARKER
        events=[];rules=[dict(enabled=True,exact=True,colors=['#112233'],tolerance=0)]*3
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'native'
            def service(owner,received,**kwargs):
                self.assertEqual(received,rules);self.assertFalse(kwargs['auto'])
                self.assertTrue((folder/ACTIVE_MARKER).is_file())
                return dict(stop_reason='target_observed')
            runner=Runner(lambda kind,data:events.append((kind,data)),folder,native_runner=service)
            with patch('engine.Game') as game,patch('engine.configure_ocr'),patch('engine.start_session_cleanup'):
                result=runner.launch(rules,strategy='native',auto=True)
            game.assert_not_called();self.assertEqual(result['stop_reason'],'target_observed')
            self.assertTrue((folder/SESSION_MARKER).is_file());self.assertFalse((folder/ACTIVE_MARKER).exists())
        self.assertEqual(sum(k=='finished' for k,d in events),1)
    def test_native_missing_service_is_rejected_before_any_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner=Runner(lambda *_:None,tmp)
            with self.assertRaisesRegex(RuntimeError,'not connected'):runner.launch([],strategy='native')
