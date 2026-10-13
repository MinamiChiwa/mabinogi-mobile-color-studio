import tempfile
import unittest
import threading
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import MagicMock, patch

import app


class AppAtlasWiringTests(unittest.TestCase):
    def test_main_window_result_detail_marks_verified_compromise(self):
        window=SimpleNamespace(cards=[SimpleNamespace(best_label=MagicMock())],
                               set_detail=MagicMock(),best_summary=None)
        row=dict(outcome='compromise',maximum=12.,average=12.,regions=[
            dict(delta=12.,color='#888888')])
        app.App.display_best(window,row)
        detail=window.set_detail.call_args.args[0]
        self.assertIn('妥协方案（未达目标）',detail)
        self.assertIn('最大色差 ΔE 12.00',detail)

    def test_stop_dismisses_completed_overlay_without_waiting_for_another_finished_event(self):
        window=SimpleNamespace(runner=None,busy=False,status=MagicMock(),overlay=MagicMock())
        app.App.stop(window)
        window.overlay.dismiss.assert_called_once()
        self.assertIn('已停止',window.status.configure.call_args.kwargs['text'])

    def test_active_stop_waits_for_worker_then_restores_ready_state(self):
        stop=threading.Event()
        window=SimpleNamespace(runner=SimpleNamespace(stop=stop),busy=True,
                               status=MagicMock(),overlay=MagicMock(),start=MagicMock())
        app.App.stop(window)
        self.assertTrue(stop.is_set());self.assertTrue(window.busy)
        window.overlay.dismiss.assert_called_once()
        app.App.finish_run(window)
        self.assertFalse(window.busy);self.assertIsNone(window.runner)
        window.start.configure.assert_called_once_with(state='normal')
        self.assertIn('已停止',window.status.configure.call_args.kwargs['text'])

    def test_visual_factory_constructs_without_game_input(self):
        with tempfile.TemporaryDirectory() as folder, patch('screenshot_live.Game') as game:
            runner=app.build_runner(lambda *_:None,folder,'atlas')
        self.assertTrue(callable(runner.screenshot_runner))
        self.assertIsNone(runner.atlas_runner)
        game.assert_not_called()

    def test_build_runner_uses_screenshot_user_rules_by_default(self):
        emit=lambda *_:None
        with tempfile.TemporaryDirectory() as folder, patch.object(app,'Runner') as runner:
            result=app.build_runner(emit,folder)
        self.assertEqual(runner.call_args.args,(emit,folder))
        self.assertTrue(callable(runner.call_args.kwargs['screenshot_runner']))
        self.assertNotIn('native_runner',runner.call_args.kwargs)
        self.assertIs(result,runner.return_value)

    def test_old_profile_visual_identifier_selects_new_screenshot_runner(self):
        from screenshot_live import run_screenshot_search
        with tempfile.TemporaryDirectory() as folder:
            runner=app.build_runner(lambda *_:None,folder,'atlas',entry=(120,340),entry_size=(1280,960))
        self.assertIs(runner.screenshot_runner,run_screenshot_search)

    def test_legacy_diagnostic_factory_keeps_screenshot_search_connection(self):
        with tempfile.TemporaryDirectory() as folder:
            runner=app.build_runner(lambda *_:None,folder,'legacy')
        self.assertTrue(callable(runner.screenshot_runner))


if __name__=='__main__':unittest.main()
