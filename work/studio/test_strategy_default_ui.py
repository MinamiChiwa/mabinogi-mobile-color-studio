"""Screenshot startup and memory-warning selector in actual five-language Tk."""
import json,sys,unittest
from pathlib import Path
import i18n

@unittest.skipUnless(sys.platform=='win32','Actual Windows Tk')
class StrategyDefaultUITests(unittest.TestCase):
    def test_default_screenshot_and_warning_survive_language_switch_and_restart(self):
        import app
        from test_native_ui_hit_testing import NativeUIHitTestingTests
        from profile_store import read_profile
        helper=NativeUIHitTestingTests();self.addCleanup(helper.doCleanups);helper.setUp()
        ui=helper.ui;original=i18n.language;self.addCleanup(i18n.set_language,original)
        self.assertEqual(ui.search_strategy.get(),'atlas')
        for language in i18n.LANGUAGES:
            ui.change_language(language);helper.pump(.02)
            options=ui.strategy_menu.cget('values')
            self.assertEqual(options[0],str(i18n.tr('截图寻色')))
            self.assertEqual(options[1],str(i18n.tr('精准寻色（读取内存，风险较高）')))
            ui.change_search_strategy(options[1]);helper.pump(.02)
            self.assertEqual(ui.search_strategy.get(),'native')
            self.assertEqual(ui.strategy_note.cget('text'),str(i18n.tr('警示：精准寻色会读取游戏内存，风险较高。')))
            ui.change_search_strategy(options[0]);helper.pump(.02)
            self.assertEqual(ui.search_strategy.get(),'atlas')
        ui.flush_autosave()
        self.assertEqual(read_profile(Path(helper.folder.name)/'profile.json')['search_strategy'],'atlas')
        self.assertEqual(helper.errors,[])

    def test_runner_default_has_no_native_service(self):
        import tempfile,app
        with tempfile.TemporaryDirectory() as folder:
            runner=app.build_runner(lambda *a:None,folder)
        self.assertIsNone(runner.native_runner)
        self.assertTrue(callable(runner.screenshot_runner))

if __name__=='__main__':unittest.main()
