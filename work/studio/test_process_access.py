"""Read-only token diagnostics retain unknowns and release owned handles."""
import importlib
import importlib.util
import unittest


class TokenAPI:
    def __init__(self, failure=None):
        self.failure = failure
        self.closed = []
        self.process_requests = []
        self.token_requests = []

    def current_process(self):
        return 900, 10  # Current-process pseudo handle is not owned.

    def open_process(self, pid, access):
        self.process_requests.append((pid, access))
        if self.failure == 'target_process':
            raise OSError(5, 'OpenProcess limited query denied')
        return 20

    def open_token(self, process, access):
        self.token_requests.append((process, access))
        if self.failure == 'target_token' and process == 20:
            raise OSError(5, 'OpenProcessToken denied')
        return {10: 100, 20: 200}[process]

    def token_elevated(self, token):
        if self.failure == 'elevation':
            raise OSError(87, 'TokenElevation unavailable')
        return token == 200

    def token_integrity(self, token):
        if self.failure == 'integrity':
            raise OSError(87, 'TokenIntegrityLevel unavailable')
        return ('medium', 8192) if token == 100 else ('high', 12288)

    def close(self, handle):
        self.closed.append(handle)


class ProcessAccessTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('process_access'),
                             'Read-only process permission diagnostics are missing')
        return importlib.import_module('process_access')

    def diagnose(self, api):
        return self.module().collect_process_access_diagnostic(901, 5, api=api)

    def test_denied_read_records_elevation_difference_without_requesting_write_access(self):
        api = TokenAPI()
        result = self.diagnose(api)
        self.assertEqual(result['operation'], 'OpenProcess')
        self.assertEqual(result['win_error'], 5)
        self.assertEqual(result['read_access'], 1040)
        self.assertEqual((result['tool_pid'], result['target_pid']), (900, 901))
        self.assertIs(result['tool_elevated'], False)
        self.assertIs(result['target_elevated'], True)
        self.assertEqual((result['tool_integrity'], result['target_integrity']), ('medium', 'high'))
        self.assertEqual((result['tool_integrity_rid'], result['target_integrity_rid']), (8192, 12288))
        self.assertEqual(api.process_requests, [(901, 4096)])
        self.assertEqual(api.token_requests, [(10, 8), (20, 8)])
        self.assertEqual(api.closed, [100, 200, 20])

    def test_target_query_denial_is_unknown_and_does_not_replace_original_error(self):
        api = TokenAPI('target_process')
        result = self.diagnose(api)
        self.assertEqual(result['win_error'], 5)
        self.assertIsNone(result['target_elevated'])
        self.assertIsNone(result['target_integrity'])
        self.assertEqual(result['target_query_errors'][0]['win_error'], 5)
        self.assertEqual(api.closed, [100])

    def test_target_token_failure_closes_its_process_handle(self):
        api = TokenAPI('target_token')
        result = self.diagnose(api)
        self.assertIsNone(result['target_elevated'])
        self.assertEqual(result['target_query_errors'][0]['win_error'], 5)
        self.assertEqual(api.closed, [100, 20])

    def test_unavailable_integrity_keeps_elevation_and_closes_every_owned_handle(self):
        api = TokenAPI('integrity')
        result = self.diagnose(api)
        self.assertIs(result['tool_elevated'], False)
        self.assertIs(result['target_elevated'], True)
        self.assertIsNone(result['target_integrity'])
        self.assertEqual(result['target_query_errors'][0]['win_error'], 87)
        self.assertEqual(api.closed, [100, 200, 20])

    def test_unavailable_elevation_keeps_integrity_without_inventing_privilege(self):
        api = TokenAPI('elevation')
        result = self.diagnose(api)
        self.assertIsNone(result['tool_elevated'])
        self.assertIsNone(result['target_elevated'])
        self.assertEqual(result['target_integrity'], 'high')
        self.assertEqual(api.closed, [100, 200, 20])


if __name__ == '__main__':
    unittest.main()
