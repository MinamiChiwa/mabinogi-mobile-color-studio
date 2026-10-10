"""Native resize surface integration on isolated tool windows only."""
import sys
import unittest
import ctypes
from ctypes import wintypes as W

import app
import test_native_ui_hit_testing as hit_testing


def emit_resize_event(surface,event,helper):
    user=surface._user
    user.NotifyWinEvent.argtypes=[W.DWORD,W.HWND,W.LONG,W.LONG]
    user.NotifyWinEvent(event,surface._hwnd,0,0)
    helper.pump(.05)


@unittest.skipUnless(sys.platform=='win32','Native window resize requires Windows')
class ResizeSurfaceTests(unittest.TestCase):
    def setUp(self):
        self.helper=hit_testing.NativeUIHitTestingTests()
        self.addCleanup(self.helper.doCleanups)
        self.helper.setUp()
        self.ui=self.helper.ui

    def test_sizing_surface_restores_live_controls_at_latest_width(self):
        from resize_surface import EVENT_SYSTEM_MOVESIZESTART,EVENT_SYSTEM_MOVESIZEEND
        surface=self.ui._resize_surface
        emit_resize_event(surface,EVENT_SYSTEM_MOVESIZESTART,self.helper)
        self.assertTrue(surface.active)
        self.assertFalse(self.ui.page.winfo_ismapped())
        self.ui.cards[0].target.set('#ABCDEF')
        self.ui.geometry('850x850+20+20');self.helper.pump(.08)
        emit_resize_event(surface,EVENT_SYSTEM_MOVESIZEEND,self.helper)
        self.helper.pump(.15)
        self.assertFalse(surface.active)
        self.assertTrue(self.ui.page.winfo_ismapped())
        self.assertEqual(self.ui._layout_columns,2)
        self.assertEqual(self.ui.cards[0].target.get(),'#ABCDEF')
        self.assertEqual(self.ui.body_scroll.winfo_manager(),'canvas')
        self.helper.hit(self.ui.cards[0].target_entry)
        self.assertEqual(self.helper.errors,[])

    def test_capture_failure_retains_normal_layout(self):
        from unittest.mock import patch
        from resize_surface import EVENT_SYSTEM_MOVESIZESTART
        surface=self.ui._resize_surface
        with patch('resize_surface.capture_client_image',side_effect=OSError('capture unavailable')):
            emit_resize_event(surface,EVENT_SYSTEM_MOVESIZESTART,self.helper)
        self.assertFalse(surface.active)
        self.assertTrue(self.ui.page.winfo_ismapped())
        self.assertEqual(self.helper.errors,[])

    def test_own_client_snapshot_contains_canvas_background(self):
        from resize_surface import capture_client_image
        image=capture_client_image(self.ui)
        self.assertEqual(image.size,(self.ui.winfo_width(),self.ui.winfo_height()))
        self.assertEqual(image.getpixel((self.ui.winfo_width()//2,5)),(16,21,31),
                         'CustomTkinter canvas backgrounds were omitted from capture')

    def test_repeated_native_gestures_preserve_scroll_and_dpi_geometry(self):
        from resize_surface import EVENT_SYSTEM_MOVESIZESTART,EVENT_SYSTEM_MOVESIZEEND
        surface=self.ui._resize_surface
        for density in (1.,.7):
            app.ct.set_widget_scaling(density)
            self.ui.geometry(f'{round(560*density)}x950+20+20');self.helper.pump(.12)
            self.ui.body_scroll._parent_canvas.yview_moveto(.25)
            self.helper.pump(.03)
            before=self.ui.body_scroll._parent_canvas.yview()[0]
            for _ in range(2):
                emit_resize_event(surface,EVENT_SYSTEM_MOVESIZESTART,self.helper)
                self.assertTrue(surface.active)
                self.ui.geometry(f'{round(600*density)}x950+20+20');self.helper.pump(.03)
                emit_resize_event(surface,EVENT_SYSTEM_MOVESIZEEND,self.helper)
                self.assertEqual(self.ui._layout_columns,1)
                self.assertAlmostEqual(self.ui.body_scroll._parent_canvas.yview()[0],before,delta=.005)
                self.assertIsNone(self.ui.grab_current())
        self.assertEqual(self.helper.errors,[])

    def test_destroy_during_gesture_unregisters_native_hook(self):
        from resize_surface import EVENT_SYSTEM_MOVESIZESTART
        surface=self.ui._resize_surface
        emit_resize_event(surface,EVENT_SYSTEM_MOVESIZESTART,self.helper)
        surface.destroy()
        self.helper.pump(.05)
        self.assertIsNone(surface._hook)
        self.assertFalse(surface.active)
        self.assertTrue(self.ui.page.winfo_ismapped())
        self.helper.hit(self.ui.cards[0].target_entry)
        self.assertEqual(self.helper.errors,[])

    def test_scaling_batch_keeps_cover_until_all_live_children_settle(self):
        surface=self.ui._resize_surface
        for scale in (1.5,1.):
            app.ct.set_widget_scaling(scale)
            self.assertTrue(surface.active)
            self.assertTrue(surface._overlay.winfo_ismapped())
            self.assertFalse(self.ui.page.winfo_ismapped())
            # Idle work is invoked inside CTk's child callbacks. It must not
            # uncover a partially updated hierarchy before the batch returns.
            self.ui.update_idletasks()
            self.assertTrue(surface.active)
            app.ct.set_window_scaling(scale)
            self.helper.pump(.08)
            self.assertFalse(surface.active)
            self.assertTrue(self.ui.page.winfo_ismapped())
            self.assertEqual(self.ui.body_scroll.winfo_manager(),'canvas')
        self.assertEqual(self.helper.errors,[])


if __name__=='__main__':unittest.main()
