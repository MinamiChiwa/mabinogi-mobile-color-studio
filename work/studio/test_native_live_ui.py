"""App selects the user-goal service without starting it during construction."""
import tempfile,unittest
from unittest.mock import patch
import app


class NativeUIConnectionTests(unittest.TestCase):
    def test_native_factory_connects_service_without_constructing_sender(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(app,'Runner') as runner:
            result=app.build_runner(lambda *_:None,tmp,'native')
        self.assertTrue(callable(runner.call_args.kwargs['native_runner']))
        self.assertIs(result,runner.return_value)
    def test_default_factory_uses_native_user_goal_service(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(app,'Runner') as runner:
            app.build_runner(lambda *_:None,tmp)
        self.assertIn('native_runner',runner.call_args.kwargs)


if __name__=='__main__':unittest.main()
