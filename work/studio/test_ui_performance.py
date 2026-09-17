import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock,patch
from ui_performance import DeliberateSlider

class ResizeTests(unittest.TestCase):
    def test_wheel_never_changes_slider_or_invokes_callback(self):
        slider=SimpleNamespace(_update_value=MagicMock())
        for delta in (-120,120):
            DeliberateSlider._mouse_scroll_event(slider,SimpleNamespace(delta=delta,num=0))
        slider._update_value.assert_not_called()

    def test_initial_density_reserves_space_for_all_controls(self):
        from app import App
        for dpi in (1,1.25,1.5,2):
            window=SimpleNamespace(_get_window_scaling=lambda:dpi,
                winfo_screenwidth=lambda:1920,winfo_screenheight=lambda:1080,
                minsize=MagicMock(),geometry=MagicMock())
            with patch('app.ct.set_widget_scaling') as scaling:
                App.fit_screen(window)
            scaling.assert_called_once_with(window._ui_scale)
            width,height=window.minsize.call_args.args
            self.assertAlmostEqual(width/height,1120/900,places=2)
            self.assertEqual(width,round(1120*window._ui_scale))

    def test_overlay_reports_search_and_recovery_without_claiming_unverified_match(self):
        from search_overlay import SearchOverlay
        rules=[dict(enabled=True,colors=['#FFFFFF'],exact=False,tolerance=8)]+[dict(enabled=False)]*2
        overlay=SimpleNamespace(rules=rules,phase='waiting',render=MagicMock(),withdraw=MagicMock())
        SearchOverlay.handle(overlay,'scene',{'colors':['#FEFEFE',None,None]})
        self.assertEqual(overlay.phase,'searching')
        self.assertIn('已达标',overlay.render.call_args.args[0])
        SearchOverlay.handle(overlay,'scene',{'colors':[None,None,None]})
        self.assertNotIn('已达标',overlay.render.call_args.args[0])
        SearchOverlay.handle(overlay,'restoring',{})
        self.assertEqual(overlay.phase,'restoring')
        SearchOverlay.handle(overlay,'finished',{})
        overlay.withdraw.assert_called_once()
