"""Pure fault injection at the live-page/snapshot handoff."""
from collections import deque
from types import SimpleNamespace
import tkinter as tk
import unittest
from unittest.mock import MagicMock,patch

from resize_surface import NativeResizeSurface


class ResizeSurfaceFaultTests(unittest.TestCase):
    def test_minimize_clears_native_owner_even_when_capture_failed(self):
        surface=self.surface();surface._events.clear();surface._native_sizing=True
        surface.window.state=lambda:'iconic';surface.window.after=MagicMock(return_value='next')
        surface._poll_events()
        self.assertFalse(surface._native_sizing)
        self.assertFalse(surface._scale_owns_surface)

    def surface(self):
        page=SimpleNamespace(mapped=True)
        page.grid_info=lambda:dict(row=0,column=0,sticky='nsew')
        page.grid_remove=lambda:setattr(page,'mapped',False)
        page.grid=lambda **kwargs:setattr(page,'mapped',True)
        window=SimpleNamespace(page=page,_resize_layout_job=None,_pending_layout_width=800,
            after_cancel=MagicMock(),reflow=MagicMock(),update_idletasks=MagicMock())
        surface=NativeResizeSurface.__new__(NativeResizeSurface)
        surface.window=window;surface.active=False;surface._closed=False;surface._capturing=False
        surface._overlay=MagicMock();surface._photo=None;surface._image_id=None;surface._page_grid=None
        surface._hook=None;surface._events=deque([10]);surface._poll_job='poll-job'
        surface._scale_job=None;surface._scale_owns_surface=False;surface._native_sizing=False
        surface._page_manager_call=None
        return surface

    def test_live_page_is_settled_before_snapshot_is_removed(self):
        surface=self.surface();surface.active=True;surface.window.page.mapped=False
        surface._page_grid=dict(row=0,column=0,sticky='nsew');events=[]
        surface.window.page.grid=lambda **kwargs:events.append('restore-page')
        surface.window.reflow=lambda:events.append('reflow')
        surface.window.update_idletasks=lambda:events.append('settle')
        surface._overlay.grid_remove.side_effect=lambda:events.append('uncover')
        surface.exit()
        self.assertLess(events.index('reflow'),events.index('uncover'))
        self.assertLess(events.index('settle'),events.index('uncover'))

    def test_scaling_finish_does_not_uncover_an_active_native_gesture(self):
        surface=self.surface();surface.active=True;surface._native_sizing=True
        surface._scale_owns_surface=True;surface.window.page.mapped=False
        surface._finish_scaling()
        self.assertTrue(surface.active)
        self.assertFalse(surface.window.page.mapped)
        self.assertFalse(surface._scale_owns_surface)

    def test_overlay_mount_failure_restores_hidden_live_page(self):
        surface=self.surface()
        surface._overlay.grid.side_effect=tk.TclError('mount failed')
        with patch('resize_surface.capture_client_image',return_value=SimpleNamespace(width=1120)),\
             patch('resize_surface.ImageTk.PhotoImage',return_value=object()):
            self.assertFalse(surface.enter())
        self.assertTrue(surface.window.page.mapped)
        self.assertFalse(surface.active)
        self.assertIsNone(surface._photo)
        self.assertIsNone(surface._image_id)

    def test_overlay_unmount_failure_still_restores_page_and_clears_snapshot(self):
        surface=self.surface();surface.active=True;surface.window.page.mapped=False
        surface._page_grid=dict(row=0,column=0,sticky='nsew');surface._photo=object();surface._image_id=1
        surface._overlay.grid_remove.side_effect=tk.TclError('already destroyed')
        surface.exit()
        self.assertTrue(surface.window.page.mapped)
        self.assertFalse(surface.active)
        self.assertIsNone(surface._photo)
        self.assertIsNone(surface._image_id)

    def test_destroy_event_cancels_poll_and_discards_queued_events(self):
        surface=self.surface()
        surface._on_destroy(SimpleNamespace(widget=surface.window))
        surface.window.after_cancel.assert_called_once_with('poll-job')
        self.assertIsNone(surface._poll_job)
        self.assertFalse(surface._events)
        self.assertTrue(surface._closed)


if __name__=='__main__':unittest.main()
