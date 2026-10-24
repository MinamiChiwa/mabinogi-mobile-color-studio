"""A native retry is a coalesced request, separate from emergency stop."""
import tempfile
import threading
import unittest
from engine import Runner


class NativeRetryBridgeTests(unittest.TestCase):
    def test_repeated_requests_are_consumed_once_and_do_not_stop_the_session(self):
        with tempfile.TemporaryDirectory() as folder:
            runner=Runner(lambda *_:None,folder)
            try:
                request=getattr(runner,'request_retry',None)
                consume=getattr(runner,'consume_retry_request',None)
                self.assertTrue(callable(request) and callable(consume),
                    'The runner needs a thread-safe retry bridge separate from stop')
                self.assertFalse(consume())
                request();request()
                self.assertTrue(consume());self.assertFalse(consume())
                self.assertFalse(runner.stop.is_set())
                runner.stop.set();request()
                self.assertFalse(consume())
            finally:runner.store.close()

    def test_hotkey_registration_contains_retry_without_polling_an_unregistered_key(self):
        import app
        import types
        from unittest.mock import patch
        owner=types.SimpleNamespace(_hotkeys_stop=threading.Event(),runner=None,q=types.SimpleNamespace(put=lambda *_:None))
        with patch.object(app,'run_hotkeys') as hotkeys:
            app.App.hotkey_loop(owner)
        self.assertIn((3,0x76),hotkeys.call_args.args[-1])


if __name__=='__main__':unittest.main()
