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

    def test_real_atlas_callback_factory_constructs_without_game_input(self):
        with tempfile.TemporaryDirectory() as folder, \
             patch('atlas_live_adapter.acquire') as capture:
            runner=app.build_runner(lambda *_:None,folder,'atlas')
        self.assertIsNotNone(runner.atlas_runner)
        capture.assert_not_called()

    def test_build_runner_uses_native_user_rules_by_default(self):
        emit=lambda *_:None
        with tempfile.TemporaryDirectory() as folder, patch.object(app,'Runner') as runner:
            result=app.build_runner(emit,folder)
        self.assertEqual(runner.call_args.args,(emit,folder))
        self.assertTrue(callable(runner.call_args.kwargs['native_runner']))
        self.assertIs(result,runner.return_value)

    def test_atlas_is_opt_in_and_waits_for_manual_entry(self):
        emit=lambda *_:None;entry=(120,340);size=(1280,960)
        service=MagicMock()
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(app,'AtlasService',return_value=service) as atlas_service, \
             patch.object(app,'atlas_callbacks',return_value='callbacks') as callbacks, \
             patch.object(app,'Runner') as runner:
            result=app.build_runner(emit,folder,'atlas',entry,size)
        callbacks.assert_called_once_with(Path(folder)/'atlas_capture',strategy='grid')
        atlas_service.assert_called_once_with('callbacks')
        runner.assert_called_once_with(emit,folder,atlas_runner=service.run)
        self.assertIs(result,runner.return_value)

    def test_atlas_does_not_require_an_entry_point(self):
        emit=lambda *_:None
        with tempfile.TemporaryDirectory() as folder, patch.object(app,'atlas_callbacks',return_value='callbacks') as callbacks, patch.object(app,'AtlasService'), patch.object(app,'Runner'):
            app.build_runner(emit,folder,'atlas')
        callbacks.assert_called_once_with(Path(folder)/'atlas_capture',strategy='grid')

    def test_configured_color_search_uses_atlas_runner(self):
        emit=lambda *_:None
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(app,'atlas_callbacks',return_value='callbacks') as callbacks, \
             patch.object(app,'AtlasService',return_value=MagicMock()) as service, \
             patch.object(app,'Runner') as runner:
            result=app.build_runner(emit,folder,'atlas')
        callbacks.assert_called_once_with(Path(folder)/'atlas_capture',strategy='grid')
        service.assert_called_once_with('callbacks')
        runner.assert_called_once_with(emit,folder,atlas_runner=service.return_value.run)
        self.assertIs(result,runner.return_value)


if __name__=='__main__':unittest.main()
