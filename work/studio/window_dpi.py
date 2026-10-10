"""Scope physical Win32 pixel coordinates without changing the UI's DPI context."""
import ctypes as C
from contextlib import contextmanager
from ctypes import wintypes as W


_u = C.WinDLL('user32', use_last_error=True)
_u.SetThreadDpiAwarenessContext.argtypes = [C.c_void_p]
_u.SetThreadDpiAwarenessContext.restype = C.c_void_p
_u.GetThreadDpiAwarenessContext.argtypes = []
_u.GetThreadDpiAwarenessContext.restype = C.c_void_p
_u.AreDpiAwarenessContextsEqual.argtypes = [C.c_void_p, C.c_void_p]
_u.AreDpiAwarenessContextsEqual.restype = W.BOOL
_u.GetWindowDpiAwarenessContext.argtypes=[W.HWND]
_u.GetWindowDpiAwarenessContext.restype=C.c_void_p


@contextmanager
def physical_pixel_context(api=None):
    """Enter PMv2 for one operation and restore the caller's exact context."""
    api = _u if api is None else api
    physical = C.c_void_p(-4)
    previous = api.SetThreadDpiAwarenessContext(physical)
    if not previous:
        raise OSError('Cannot enter physical per-monitor DPI context')
    try:
        if not api.AreDpiAwarenessContextsEqual(api.GetThreadDpiAwarenessContext(), physical):
            raise OSError('Physical per-monitor DPI context unavailable')
        yield
    finally:
        if not api.SetThreadDpiAwarenessContext(C.c_void_p(previous)):
            raise OSError('Cannot restore caller DPI context')


@contextmanager
def target_pixel_context(hwnd,api=None):
    """Use the window's API units before explicit conversion to physical pixels."""
    api=_u if api is None else api
    target=api.GetWindowDpiAwarenessContext(hwnd)
    if not target:raise OSError('Target window DPI context unavailable')
    previous=api.SetThreadDpiAwarenessContext(C.c_void_p(target))
    if not previous:raise OSError('Cannot enter target window DPI context')
    try:
        if not api.AreDpiAwarenessContextsEqual(api.GetThreadDpiAwarenessContext(),C.c_void_p(target)):
            raise OSError('Target window DPI context unconfirmed')
        yield
    finally:
        if not api.SetThreadDpiAwarenessContext(C.c_void_p(previous)):
            raise OSError('Cannot restore caller DPI context')
