"""A denied process read is actionable and stops before game acquisition."""
import ctypes
import importlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from native_live import runtime_read, service
from native_status import result_text


class DeniedKernel:
    def __init__(self, error=5):
        self.requests = []
        self.error = error

    def OpenProcess(self, access, inherit, pid):
        self.requests.append((access, inherit, pid))
        ctypes.set_last_error(self.error)
        return None


class NativeProcessAccessTests(unittest.TestCase):
    def test_reader_denial_is_classified_with_original_error_and_read_mask(self):
        kernel = DeniedKernel()
        with patch.object(runtime_read, 'K', kernel), \
             patch('process_access.collect_process_access_diagnostic', return_value={}), \
             self.assertRaises(OSError) as raised:
            runtime_read.Reader(987)
        error = raised.exception
        self.assertEqual(type(error).__name__, 'ProcessReadDenied')
        self.assertEqual(error.errno, 5)
        self.assertEqual(error.diagnostic['win_error'], 5)
        self.assertEqual(error.diagnostic['read_access'], 1040)
        self.assertEqual(error.diagnostic['target_pid'], 987)
        self.assertEqual(kernel.requests, [(1040, False, 987)])
        self.assertEqual(service.unavailable_reason(error), 'process_access')

    def test_diagnostic_collection_failure_cannot_hide_original_denial(self):
        kernel = DeniedKernel()
        with patch.object(runtime_read, 'K', kernel), \
             patch('process_access.collect_process_access_diagnostic', side_effect=RuntimeError('diagnostic failed')), \
             self.assertRaises(OSError) as raised:
            runtime_read.Reader(987)
        error = raised.exception
        self.assertEqual(error.errno, 5)
        self.assertEqual(error.diagnostic['win_error'], 5)
        self.assertIsNone(error.diagnostic['target_elevated'])

    def test_other_openprocess_errors_are_preserved_without_permission_guesses(self):
        kernel = DeniedKernel(87)
        with patch.object(runtime_read, 'K', kernel), \
             patch('process_access.collect_process_access_diagnostic') as diagnose, \
             self.assertRaises(OSError) as raised:
            runtime_read.Reader(987)
        self.assertEqual(raised.exception.errno, 87)
        self.assertNotEqual(service.unavailable_reason(raised.exception), 'process_access')
        diagnose.assert_not_called()

    def test_preparation_file_failure_cannot_replace_the_original_process_denial(self):
        module = importlib.import_module('process_access')
        error = module.ProcessReadDenied(901, 5, diagnostic={})
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(service, 'configure_ocr'), \
             patch.object(service, 'prepare_timer_assets', return_value={}), \
             patch.object(service, 'prepare_hex_assets', return_value={}), \
             patch.object(service, 'CurrentBuildBackend', side_effect=error), \
             patch.object(Path, 'write_text', side_effect=[None, OSError(112, 'Disk full')]), \
             self.assertRaises(OSError) as raised:
            service._prepare(901, Path(tmp), lambda: None)
        self.assertIs(raised.exception, error)
        self.assertEqual(raised.exception.errno, 5)

    def test_preparation_saves_permission_diagnostics_before_any_sender_or_palette_capture(self):
        module = importlib.import_module('process_access')
        diagnostic = dict(operation='OpenProcess', win_error=5, read_access=1040,
                          tool_pid=900, target_pid=901, tool_elevated=False, target_elevated=True)
        error = module.ProcessReadDenied(901, 5, diagnostic=diagnostic)
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(service, 'configure_ocr'), \
             patch.object(service, 'prepare_timer_assets', return_value={}), \
             patch.object(service, 'prepare_hex_assets', return_value={}), \
             patch.object(service, 'CurrentBuildBackend', side_effect=error), \
             patch.object(service, 'ProjectClosedLoopIO') as sender, \
             patch.object(service, 'collect_validation_session') as capture:
            result = service.preflight(901, Path(tmp))
            saved = json.loads((Path(tmp) / 'native-preparation.json').read_text(encoding='utf-8'))
        self.assertEqual(result['unavailable_reason'], 'process_access')
        self.assertEqual(result['actual_input_attempts'], 0)
        self.assertEqual(saved['process_access']['win_error'], 5)
        self.assertEqual(saved['process_access']['target_elevated'], True)
        self.assertEqual(saved['inputs_sent'], 0)
        sender.assert_not_called()
        capture.assert_not_called()

    def test_permission_failure_is_explained_before_generic_game_or_window_failures(self):
        title, detail = result_text(dict(stop_reason='unavailable', unavailable_reason='process_access'))
        self.assertIn('权限', title)
        self.assertIn('相同权限', detail)
        self.assertIn('管理员', detail)
        self.assertIn('普通界面', detail)


if __name__ == '__main__':
    unittest.main()
