"""Read-only CLI must preserve the selected HWND, including high-DPI windows."""
import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import native_preflight
from window_target import WindowTarget


class NativePreflightTargetTests(unittest.TestCase):
    def test_automatic_target_preserves_handle_in_preflight(self):
        with tempfile.TemporaryDirectory() as tmp,patch('window_target.resolve_target',return_value=WindowTarget(30,40,'Game')), \
            patch('native_live.service.preflight',return_value={'stop_reason':'preflight_complete'}) as preflight:
            self.assertEqual(native_preflight.main(['--output-dir',tmp]),0)
        self.assertEqual(preflight.call_args.args,(40,Path(tmp)))
        self.assertEqual(preflight.call_args.kwargs.get('hwnd'),30)
    def test_explicit_pid_does_not_silently_pick_a_different_process(self):
        with tempfile.TemporaryDirectory() as tmp,patch('window_target.resolve_target') as resolve, \
            patch('native_live.service.preflight',return_value={'stop_reason':'preflight_complete'}) as preflight:
            native_preflight.main(['--pid','40','--output-dir',tmp])
        resolve.assert_not_called()
        self.assertEqual(preflight.call_args.args[0],40)
    def test_explicit_window_target_can_be_passed_for_selected_process(self):
        with tempfile.TemporaryDirectory() as tmp,patch('window_target.resolve_target') as resolve, \
            patch('native_live.service.preflight',return_value={'stop_reason':'preflight_complete'}) as preflight:
            native_preflight.main(['--pid','40','--hwnd','30','--output-dir',tmp])
        resolve.assert_not_called();self.assertEqual(preflight.call_args.kwargs['hwnd'],30)


if __name__=='__main__':unittest.main()
