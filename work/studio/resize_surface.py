"""A single bitmap during Windows sizing; live controls return on release.

The application's Tk hierarchy contains hundreds of native child windows.
Moving them for every frame is expensive even with fixed-size cards. A client
PrintWindow snapshot keeps that hierarchy still during the gesture. This is
local to this window: no global redraw suppression or mouse input is used.
"""
import ctypes
from ctypes import wintypes as W
import sys
import tkinter as tk
import os
from collections import deque
from PIL import Image, ImageTk

GA_ROOT=2
EVENT_SYSTEM_MOVESIZESTART=0x000A
EVENT_SYSTEM_MOVESIZEEND=0x000B


def _window_api():
    user=ctypes.WinDLL('user32',use_last_error=True)
    gdi=ctypes.WinDLL('gdi32',use_last_error=True)
    user.GetDC.argtypes=[W.HWND];user.GetDC.restype=W.HDC
    user.ReleaseDC.argtypes=[W.HWND,W.HDC];user.ReleaseDC.restype=ctypes.c_int
    user.GetClientRect.argtypes=[W.HWND,ctypes.POINTER(W.RECT)];user.GetClientRect.restype=W.BOOL
    user.GetAncestor.argtypes=[W.HWND,W.UINT];user.GetAncestor.restype=W.HWND
    user.PrintWindow.argtypes=[W.HWND,W.HDC,W.UINT];user.PrintWindow.restype=W.BOOL
    gdi.CreateCompatibleDC.argtypes=[W.HDC];gdi.CreateCompatibleDC.restype=W.HDC
    gdi.CreateCompatibleBitmap.argtypes=[W.HDC,ctypes.c_int,ctypes.c_int];gdi.CreateCompatibleBitmap.restype=W.HBITMAP
    gdi.SelectObject.argtypes=[W.HDC,W.HGDIOBJ];gdi.SelectObject.restype=W.HGDIOBJ
    gdi.DeleteObject.argtypes=[W.HGDIOBJ];gdi.DeleteObject.restype=W.BOOL
    gdi.DeleteDC.argtypes=[W.HDC];gdi.DeleteDC.restype=W.BOOL
    gdi.GetDIBits.argtypes=[W.HDC,W.HBITMAP,W.UINT,W.UINT,ctypes.c_void_p,ctypes.c_void_p,W.UINT]
    gdi.GetDIBits.restype=ctypes.c_int
    return user,gdi


class _BitmapInfo(ctypes.Structure):
    _fields_=[('size',W.DWORD),('width',W.LONG),('height',W.LONG),
              ('planes',W.WORD),('bits',W.WORD),('compression',W.DWORD),
              ('image_size',W.DWORD),('xppm',W.LONG),('yppm',W.LONG),
              ('used',W.DWORD),('important',W.DWORD),('colors',W.DWORD*3)]


def capture_client_image(window):
    """Render only this Tk client and descendants into an owned bitmap."""
    user,gdi=_window_api();hwnd=window.winfo_id()
    rect=W.RECT()
    if not user.GetClientRect(hwnd,ctypes.byref(rect)):raise OSError('client unavailable')
    width,height=rect.right,rect.bottom
    if not 0<width<=16384 or not 0<height<=16384 or width*height>33554432:
        raise OSError('invalid client size')
    dc=memory=bitmap=previous=None
    try:
        dc=user.GetDC(hwnd);memory=gdi.CreateCompatibleDC(dc)
        bitmap=gdi.CreateCompatibleBitmap(dc,width,height)
        if not dc or not memory or not bitmap:raise OSError('bitmap allocation failed')
        previous=gdi.SelectObject(memory,bitmap)
        # PW_RENDERFULLCONTENT asks DWM to render layered/transparent child
        # surfaces (CustomTkinter's canvases otherwise appear black).
        if not user.PrintWindow(hwnd,memory,2):raise OSError('client rendering unavailable')
        gdi.SelectObject(memory,previous);previous=None
        info=_BitmapInfo(size=40,width=width,height=-height,planes=1,bits=32)
        data=ctypes.create_string_buffer(width*height*4)
        if gdi.GetDIBits(memory,bitmap,0,height,data,ctypes.byref(info),0)!=height:
            raise OSError('client bitmap read failed')
        return Image.frombuffer('RGB',(width,height),data,'raw','BGRX',0,1).copy()
    finally:
        if previous and memory:gdi.SelectObject(memory,previous)
        if bitmap:gdi.DeleteObject(bitmap)
        if memory:gdi.DeleteDC(memory)
        if dc:user.ReleaseDC(hwnd,dc)


class NativeResizeSurface:
    def __init__(self,window):
        self.window=window;self.active=False;self._capturing=False;self._closed=False
        self._photo=None;self._image_id=None;self._hook=None;self._callback=None
        self._page_grid=None
        self._page_manager_call=None
        self._events=deque();self._poll_job=None
        self._scale_job=None;self._scale_owns_surface=False
        self._native_sizing=False
        self._overlay=tk.Canvas(window,highlightthickness=0,borderwidth=0,bg='#10151F')
        self._overlay.bind('<Configure>',self._position_image)
        self._destroy_binding=window.bind('<Destroy>',self._on_destroy,add='+')
        if sys.platform=='win32':self._install_hook()
        self._poll_job=window.after(16,self._poll_events)

    def _install_hook(self):
        try:
            self._user,_=_window_api()
            callback_type=ctypes.WINFUNCTYPE(None,ctypes.c_void_p,W.DWORD,W.HWND,W.LONG,W.LONG,W.DWORD,W.DWORD)
            self._callback=callback_type(self._win_event)
            self._hwnd=self._user.GetAncestor(self.window.winfo_id(),GA_ROOT)
            self._user.SetWinEventHook.argtypes=[W.DWORD,W.DWORD,ctypes.c_void_p,callback_type,W.DWORD,W.DWORD,W.DWORD]
            self._user.SetWinEventHook.restype=ctypes.c_void_p
            self._user.UnhookWinEvent.argtypes=[ctypes.c_void_p];self._user.UnhookWinEvent.restype=W.BOOL
            self._hook=self._user.SetWinEventHook(EVENT_SYSTEM_MOVESIZESTART,EVENT_SYSTEM_MOVESIZEEND,None,
                self._callback,os.getpid(),0,0)
            if not self._hook:raise OSError('resize event hook unavailable')
        except (OSError,AttributeError):
            self._hook=None;self._callback=None

    def _win_event(self,hook,event,hwnd,object_id,child_id,thread,time):
        # The callback must not call Tcl/Tk: it may run while _tkinter owns
        # Tcl's event-loop thread state. A normal Tk timer drains this queue.
        if hwnd!=self._hwnd or self._closed or object_id!=0:return
        self._events.append(event)

    def _poll_events(self):
        self._poll_job=None
        if self._closed:return
        try:
            while self._events:
                event=self._events.popleft()
                if event==EVENT_SYSTEM_MOVESIZESTART:
                    self._native_sizing=True;self.enter()
                else:
                    self._native_sizing=False
                    if not self._scale_owns_surface:self.exit()
            # Minimize/close can cancel the gesture before its end event.
            if self.window.state()=='iconic':
                self._native_sizing=False;self._scale_owns_surface=False;self.exit()
        except (tk.TclError,RuntimeError):
            self._native_sizing=False;self._scale_owns_surface=False;self.exit()
        finally:
            if not self._closed:
                try:self._poll_job=self.window.after(16,self._poll_events)
                except tk.TclError:self._closed=True

    def _position_image(self,event=None):
        if self._image_id is not None and self._photo is not None:
            width=event.width if event is not None else self._overlay.winfo_width()
            self._overlay.coords(self._image_id,width//2,0)

    def enter(self):
        if self.active or self._closed or self._capturing:return False
        self._capturing=True
        try:
            image=capture_client_image(self.window)
            self._photo=ImageTk.PhotoImage(image,master=self.window)
        except Exception:
            self._photo=None;return False
        finally:self._capturing=False
        job=getattr(self.window,'_resize_layout_job',None)
        if job is not None:
            try:self.window.after_cancel(job)
            except tk.TclError:pass
            self.window._resize_layout_job=None
        self._overlay.delete('all')
        self._image_id=self._overlay.create_image(image.width//2,0,anchor='n',image=self._photo)
        self._page_grid=dict(self.window.page.grid_info())
        self._page_manager_call=getattr(self.window.page,'_last_geometry_manager_call',None)
        # CTk reapplies this cached grid during its own _set_scaling callback.
        # Clearing it keeps the live hierarchy hidden for the entire batch.
        self.window.page._last_geometry_manager_call=None
        try:
            self.window.page.grid_remove()
            self._overlay.grid(row=0,column=0,sticky='nsew')
        except (tk.TclError,RuntimeError):
            # A close or another geometry callback may race this boundary.
            # Never leave the live page hidden when the snapshot cannot mount.
            try:self._overlay.grid_remove()
            except tk.TclError:pass
            self._clear_snapshot()
            self._restore_page()
            self._page_grid=None
            return False
        self.active=True
        return True

    def sizing(self):
        return self.active

    def hold_scaling(self):
        """Cover the synchronous CTk scaling callback batch until it settles."""
        if self._closed:return
        if self._scale_job is not None:
            try:self.window.after_cancel(self._scale_job)
            except tk.TclError:pass
        if not self.active and self.enter():
            self._scale_owns_surface=True
            # Mount the cover before CTk proceeds to the rest of the child
            # callbacks. An idle-only mount still exposed their old canvases.
            self.window.update_idletasks()
        # A timer runs only after the synchronous scaling batch returns;
        # after_idle could be drained by a child's own update_idletasks().
        self._scale_job=self.window.after(0,self._finish_scaling)

    def _finish_scaling(self):
        self._scale_job=None
        if self._closed:return
        if self._scale_owns_surface:
            self._scale_owns_surface=False
            if not self._native_sizing:self.exit()
        # An ordinary native sizing gesture owns its own end boundary. A DPI
        # callback must not uncover that gesture early.

    def exit(self):
        if not self.active:return
        self.active=False
        # Rebuild and settle every live child while the old frame still covers
        # the window. Removing the cover first exposes half-applied Tk geometry
        # and was the source of the visible duplicate/fragmented frames.
        self._restore_page()
        self.window._pending_layout_width=None
        try:self.window.reflow()
        except (tk.TclError,RuntimeError):pass
        try:self.window.update_idletasks()
        except tk.TclError:pass
        try:self._overlay.grid_remove()
        except tk.TclError:pass
        self._clear_snapshot();self._page_grid=None

    def _clear_snapshot(self):
        try:self._overlay.delete('all')
        except tk.TclError:pass
        self._image_id=None;self._photo=None

    def _restore_page(self):
        if self._closed:return
        try:
            self.window.page._last_geometry_manager_call=self._page_manager_call
            if self._page_grid is None:self.window.page.grid(row=0,column=0,sticky='nsew')
            else:
                grid=dict(self._page_grid);grid.pop('in',None)
                self.window.page.grid(**grid)
        except (tk.TclError,RuntimeError):pass

    def _remove_hook(self):
        if self._hook:
            try:self._user.UnhookWinEvent(self._hook)
            except (OSError,AttributeError):pass
            self._hook=None

    def _on_destroy(self,event):
        if event.widget is self.window:
            self._closed=True;self.active=False;self._remove_hook()
            self._events.clear();self._image_id=None;self._photo=None;self._page_grid=None
            if self._scale_job is not None:
                try:self.window.after_cancel(self._scale_job)
                except tk.TclError:pass
                self._scale_job=None
            if self._poll_job is not None:
                try:self.window.after_cancel(self._poll_job)
                except tk.TclError:pass
                self._poll_job=None

    def destroy(self):
        if self._closed:return
        self.exit();self._remove_hook();self._closed=True
        if self._scale_job is not None:
            try:self.window.after_cancel(self._scale_job)
            except tk.TclError:pass
            self._scale_job=None
        if self._poll_job is not None:
            try:self.window.after_cancel(self._poll_job)
            except tk.TclError:pass
            self._poll_job=None
        self._overlay.destroy()
