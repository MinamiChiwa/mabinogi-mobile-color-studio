import unittest,threading,tempfile
from unittest.mock import patch,MagicMock
from window_target import WindowTarget,choose_auto,resolve_target,valid_target,WindowUnavailable
from platform_win import Game,Interrupted

class WindowTargetTests(unittest.TestCase):
    def test_title_variants_and_process_fallback(self):
        for title in ('瑪奇 Mobile','瑪奇Mobile','瑪奇　Ｍｏｂｉｌｅ','玛奇 mobile','Mabinogi Mobile'):
            w=WindowTarget(10,20,title)
            self.assertEqual(choose_auto([w]),w)
        w=WindowTarget(11,21,'Custom game title','MabinogiMobile.exe')
        self.assertEqual(choose_auto([w]),w)
    def test_does_not_select_tool_or_browser_by_partial_title(self):
        with self.assertRaises(WindowUnavailable):choose_auto([WindowTarget(1,2,'染色工坊 · 瑪奇 Mobile','ColorStudio.exe'),WindowTarget(3,4,'瑪奇Mobile - Microsoft Edge','msedge.exe')])
    def test_multiple_candidates_require_selection_or_foreground(self):
        a=WindowTarget(1,2,'瑪奇Mobile');b=WindowTarget(3,4,'瑪奇 Mobile')
        with self.assertRaises(WindowUnavailable):choose_auto([a,b])
        self.assertEqual(choose_auto([a,b],3),b)
    def test_manual_window_does_not_depend_on_title(self):
        target=WindowTarget(1,2,'Different title')
        with patch('window_target.valid_target',return_value=True),patch('window_target.list_windows') as listing:
            self.assertEqual(resolve_target(target),target);listing.assert_not_called()
    def test_recycled_handle_for_other_process_is_rejected(self):
        with patch('window_target.u.IsWindow',return_value=True),patch('window_target.window_pid',return_value=9):
            self.assertFalse(valid_target(WindowTarget(1,2,'Game')))
    def test_closed_manual_window_never_switches_to_auto(self):
        game=Game.__new__(Game);game.target=WindowTarget(1,2,'Game');game.manual_target=game.target;game.hwnd=1;game.stop=threading.Event()
        with patch('platform_win.valid_target',return_value=False),patch('platform_win.resolve_target') as resolve:
            with self.assertRaises(WindowUnavailable):game.capture_waiting()
            resolve.assert_not_called()
    def test_worker_passes_same_selection_and_activates_once(self):
        from engine import Runner
        target=WindowTarget(1,2,'Game');game=MagicMock();game.hwnd=1
        with tempfile.TemporaryDirectory() as folder,patch('engine.configure_ocr'),patch('engine.Game',return_value=game) as constructor,patch('platform_win.u.GetDpiForWindow',return_value=96),patch('window_target.window_title',return_value='Game'):
            runner=Runner(lambda *args:None,folder)
            with patch.object(runner,'wait_for_board',side_effect=Interrupted('test')):runner.launch([],activate=True,target=target)
        constructor.assert_called_once_with(runner.stop,target=target);game.focus.assert_called_once()

    def test_borderless_client_geometry_preserves_screen_origin(self):
        import platform_win as win
        game=Game.__new__(Game);game.target=WindowTarget(1,2,'Game');game.hwnd=1
        def client(hwnd,p):
            p._obj.left=0;p._obj.top=0;p._obj.right=1920;p._obj.bottom=1080;return True
        def origin(hwnd,p):p._obj.x=-1920;p._obj.y=0;return True
        with patch('platform_win.valid_target',return_value=True),patch.object(win.u,'IsIconic',return_value=False),patch.object(win.u,'GetClientRect',side_effect=client),patch.object(win.u,'ClientToScreen',side_effect=origin):
            self.assertEqual(game.geometry(),(-1920,0,1920,1080))

    def test_active_ui_messages_have_english_translations(self):
        import ast,re,i18n
        from pathlib import Path
        original=i18n.language;i18n.language='English'
        try:
            for name in ('app.py','engine.py','search_overlay.py','window_picker.py','platform_win.py','palette_viewer.py','eyedropper.py'):
                for node in ast.walk(ast.parse((Path(__file__).parent/name).read_text(encoding='utf-8'))):
                    if not isinstance(node,ast.Constant) or not isinstance(node.value,str):continue
                    if node.value in ('简体中文','繁體中文'):continue
                    translated=i18n.tr(node.value).replace('南千和','')
                    self.assertIsNone(re.search('[\u4e00-\u9fff]',translated),(name,node.lineno,node.value))
        finally:i18n.language=original
