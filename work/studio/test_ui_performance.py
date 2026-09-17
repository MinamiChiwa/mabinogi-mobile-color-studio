import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock
from customtkinter.windows.widgets.core_widget_classes import CTkBaseClass
from ui_performance import install_resize_coalescing

class ResizeTests(unittest.TestCase):
    def test_resize_burst_draws_latest_size_once_at_scaled_dimensions(self):
        install_resize_coalescing()
        widget=SimpleNamespace(_current_width=100,_current_height=80,
            _reverse_widget_scaling=lambda v:v/1.5,after=MagicMock(return_value='job'),_draw=MagicMock())
        for width in (180,210,240):
            CTkBaseClass._update_dimensions_event(widget,SimpleNamespace(width=width,height=150))
        widget.after.assert_called_once()
        self.assertEqual((widget._current_width,widget._current_height),(160,100))
        widget.after.call_args.args[1]()
        widget._draw.assert_called_once_with(no_color_updates=True)
        self.assertIsNone(widget._studio_resize_job)
        CTkBaseClass._update_dimensions_event(widget,SimpleNamespace(width=240,height=150))
        widget.after.assert_called_once()
