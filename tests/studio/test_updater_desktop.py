"""Actual isolated Tk update controls; no game or network access."""
import sys,unittest
from test_native_ui_hit_testing import NativeUIHitTestingTests

@unittest.skipUnless(sys.platform=='win32','Desktop UI requires Windows')
class UpdateDesktopTests(unittest.TestCase):
    def test_three_languages_and_busy_install_leave_search_running(self):
        import app
        original_language=app.i18n.language
        self.addCleanup(lambda:setattr(app.i18n,'language',original_language))
        from updater.types import Manifest,UpdatePlan
        helper=NativeUIHitTestingTests();helper.setUp();self.addCleanup(helper.doCleanups)
        ui=helper.ui;updates=ui.update_ui;runtime=ui.updater
        runtime.service.manifest=Manifest.for_test('0.4.3',())
        runtime.service.mark_ready(UpdatePlan(new_version='0.4.3',download_bytes=1000))
        ui.busy=True
        for language in ('简体中文','繁體中文','English','日本語','한국어'):
            app.i18n.set_language(language);updates.open();updates.handle(dict(kind='ready',version='0.4.3'))
            helper.pump(.1)
            self.assertEqual(updates.actions['install'].cget('state'),'disabled')
            self.assertIn('0.4.3',updates.heading.cget('text'))
            updates.install();self.assertEqual(runtime.service.state,'ready');self.assertTrue(ui.busy)
            updates.dialog.destroy();helper.pump(.02)
        ui.busy=False;ui._window_selecting=True
        updates.open();updates.handle(dict(kind='ready',version='0.4.3'))
        self.assertEqual(updates.actions['install'].cget('state'),'disabled')
        updates.install();self.assertTrue(runtime.service.busy);self.assertEqual(runtime.service.state,'ready')
        updates.dialog.destroy()
        self.assertEqual(helper.errors,[])
