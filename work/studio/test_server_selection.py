"""Server selection follows the window identity and exact registered build."""
import tempfile,threading,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch

from window_target import WindowTarget,choose_auto,resolve_target,WindowUnavailable,MultipleWindows
from native_live import service,build_adapters as builds


class ServerSelectionTests(unittest.TestCase):
    windows=[WindowTarget(1,10,'瑪奇Mobile','MabinogiMobile.exe'),
             WindowTarget(2,20,'마비노기 모바일','MabinogiMobile.exe'),
             WindowTarget(3,30,'マビモバ','MabinogiMobile.exe')]

    def test_selected_server_wins_over_other_servers_foreground(self):
        for server,window in zip(('tw','kr','jp'),self.windows):
            with self.subTest(server=server):
                self.assertEqual(choose_auto(self.windows,foreground=1,server=server),window)

    def test_absent_server_cannot_fall_back_to_known_other_server(self):
        with self.assertRaises(WindowUnavailable):choose_auto(self.windows[:2],server='jp')
        custom=WindowTarget(4,40,'Custom title','MabinogiMobile.exe')
        self.assertEqual(choose_auto([*self.windows[:2],custom],server='jp'),custom)
        with self.assertRaises(MultipleWindows):
            choose_auto([custom,WindowTarget(5,50,'Another custom title','MabinogiMobile.exe')],server='jp')

    def test_resolve_filters_automatic_choice_and_preserves_explicit_identity(self):
        with patch('window_target.list_windows',return_value=self.windows),patch('window_target.u.GetForegroundWindow',return_value=1):
            self.assertEqual(resolve_target(server='jp'),self.windows[2])
        with patch('window_target.valid_target',return_value=True),patch('window_target.list_windows') as listing:
            self.assertEqual(resolve_target(self.windows[1],server='jp'),self.windows[1])
            listing.assert_not_called()  # The service checks the actual build, not display text.

    def test_ui_selection_enables_only_its_exact_registered_build(self):
        rules=[dict(enabled=True,exact=True,colors=['#FFFFFF'],tolerance=8)]*3
        for server,adapter in zip(('tw','kr','jp'),builds.KNOWN):
            for actual in builds.KNOWN:
                with self.subTest(server=server,actual=actual.adapter_id),tempfile.TemporaryDirectory() as folder:
                    owner=SimpleNamespace(folder=Path(folder),stop=threading.Event(),event=Mock())
                    backend=SimpleNamespace(adapter=actual,close=Mock())
                    with patch.object(service.sys,'argv',['ColorStudio.exe']),patch.object(service,'resolve_target',return_value=self.windows[0]), \
                        patch.object(service,'_prepare',return_value=(backend,{})), \
                        patch.object(service,'collect_validation_session',return_value={'stop_reason':'no_active_palette_timeout'}) as collect:
                        result=service.run_native_search(owner,rules,server=server)
                    self.assertEqual(bool(collect.call_count),actual==adapter)
                    self.assertEqual(result['actual_input_attempts'],0)
                    if actual==adapter:self.assertEqual(result['selected_server'],server)

    def test_unregistered_or_modified_build_cannot_be_enabled_by_ui(self):
        from dataclasses import replace
        for adapter in (None,replace(builds.JP_ADAPTER,palette_class_rva=0x1000)):
            with self.subTest(adapter=adapter),self.assertRaises(ValueError):
                builds.enable_selected_server_input(SimpleNamespace(adapter=adapter),'jp')

    def test_current_ui_selection_takes_precedence_over_legacy_launch_flag(self):
        with tempfile.TemporaryDirectory() as folder:
            owner=SimpleNamespace(folder=Path(folder),stop=threading.Event(),event=Mock())
            backend=SimpleNamespace(adapter=builds.JP_ADAPTER,close=Mock())
            with patch.object(service.sys,'argv',['ColorStudio.exe','--validate-korean-build']), \
                patch.object(service,'resolve_target',return_value=self.windows[2]), \
                patch.object(service,'_prepare',return_value=(backend,{})), \
                patch.object(service,'collect_validation_session',return_value={'stop_reason':'no_active_palette_timeout'}) as collect:
                result=service.run_native_search(owner,[dict(enabled=True,exact=True,colors=['#FFFFFF'],tolerance=8)]*3,server='jp')
            self.assertEqual(collect.call_count,1);self.assertEqual(result['actual_input_attempts'],0)

    def test_mismatched_server_is_explained_as_selection_problem(self):
        from native_status import result_text
        exc=ValueError('所选服务器与客户端版本不匹配，请检查服务器和游戏窗口。')
        reason=service.unavailable_reason(exc)
        self.assertEqual(reason,'server_selection')
        title,body=result_text(dict(stop_reason='unavailable',unavailable_reason=reason))
        self.assertIn('服务器',title);self.assertIn('窗口',body)

    def test_ui_server_choice_resets_window_and_preserves_other_preferences(self):
        import app
        from ui_settings import read_settings
        for busy in (False,True):
            with self.subTest(busy=busy),tempfile.TemporaryDirectory() as folder:
                server=SimpleNamespace(get=lambda:'tw',set=Mock())
                ui=SimpleNamespace(server=server,busy=busy,server_menu=Mock(),selected_window=self.windows[0],
                    refresh_window_label=Mock(),status=Mock())
                with patch.object(app,'DATA',Path(folder)):
                    app.App.change_server(ui,str(app.tr('日服')))
                if busy:
                    server.set.assert_not_called();self.assertEqual(ui.selected_window,self.windows[0])
                else:
                    server.set.assert_called_once_with('jp');self.assertIsNone(ui.selected_window)
                    ui.refresh_window_label.assert_called_once()
                    self.assertEqual(read_settings(Path(folder)/'settings.json')['server'],'jp')

    def test_visual_search_uses_same_server_window_selection(self):
        import screenshot_live
        import numpy as np
        owner=SimpleNamespace(stop=threading.Event(),event=Mock())
        factory=Mock();factory.return_value.capture_waiting.return_value=np.full((100,100,3),255,dtype=np.uint8)
        scene=SimpleNamespace(cards=[(1,1,10,10)])
        with patch.object(screenshot_live,'resolve_target',return_value=self.windows[2]) as resolve, \
             patch.object(screenshot_live,'recognize',return_value=scene):
            screenshot_live._wait_board(owner,factory,None,False,server='jp')
        resolve.assert_called_once_with(None,server='jp')
        factory.assert_called_once_with(owner.stop,target=self.windows[2])

    def test_window_picker_is_single_and_stale_server_callback_is_ignored(self):
        import app
        value=['tw'];server=SimpleNamespace(get=lambda:value[0],set=lambda v:value.__setitem__(0,v))
        ui=SimpleNamespace(server=server,busy=False,selected_window=None,status=Mock(),refresh_window_label=Mock())
        with patch.object(app,'WindowPicker') as factory:
            app.App.pick_window(ui);callback=factory.call_args.args[2]
            app.App.pick_window(ui)
            self.assertEqual(factory.call_count,1)
            value[0]='jp';callback(self.windows[0])
            self.assertIsNone(ui.selected_window)

    def test_update_installation_cannot_leave_server_menu_out_of_sync(self):
        import app
        ui=SimpleNamespace(server=SimpleNamespace(get=lambda:'tw',set=Mock()),busy=False,server_menu=Mock(),
            updater=SimpleNamespace(service=SimpleNamespace(state='installing')))
        app.App.change_server(ui,str(app.tr('日服')))
        ui.server_menu.set.assert_called_once_with(str(app.tr('台服')))


class ServerSelectionDesktopTests(unittest.TestCase):
    def test_real_toolbar_remains_usable_and_server_setting_is_saved(self):
        import app,test_native_ui_hit_testing as fixtures
        helper=fixtures.NativeUIHitTestingTests();self.addCleanup(helper.doCleanups);helper.setUp()
        ui=helper.ui
        self.assertEqual(ui.server.get(),'tw');self.assertEqual(ui.search_strategy.get(),'atlas')
        ui.change_server(str(app.tr('日服')));helper.pump(.05)
        self.assertEqual(ui.server.get(),'jp')
        for width in (560,850,1120):
            ui.geometry(f'{width}x850+20+20');helper.pump(.15)
            helper.hit(ui.server_menu);helper.hit(ui.window_button)
            self.assertEqual(ui.server_menu.master,ui.window_button.master)
        self.assertEqual(helper.errors,[])
        from ui_settings import read_settings
        self.assertEqual(read_settings(Path(helper.folder.name)/'settings.json')['server'],'jp')


if __name__=='__main__':unittest.main()
