"""Native status overlay policy and serialized capture protection."""
import ctypes as C
from ctypes import wintypes as W
from contextlib import contextmanager
import threading


_u=C.WinDLL('user32',use_last_error=True)
for name,args,result in (
    ('GetWindowLongPtrW',[W.HWND,C.c_int],C.c_ssize_t),
    ('SetWindowLongPtrW',[W.HWND,C.c_int,C.c_ssize_t],C.c_ssize_t),
    ('SetWindowPos',[W.HWND,W.HWND,C.c_int,C.c_int,C.c_int,C.c_int,W.UINT],W.BOOL),
    ('SetWindowDisplayAffinity',[W.HWND,W.DWORD],W.BOOL),
    ('GetWindowDisplayAffinity',[W.HWND,C.POINTER(W.DWORD)],W.BOOL),
    ('IsWindow',[W.HWND],W.BOOL),('IsWindowVisible',[W.HWND],W.BOOL),
    ('ShowWindow',[W.HWND,C.c_int],W.BOOL)):
    function=getattr(_u,name);function.argtypes=args;function.restype=result
_lock=threading.RLock()
_capture_lock=threading.RLock()
_overlays={}


def register_overlay(hwnd,*,capture_excluded):
    with _lock:
        existing=_overlays.get(int(hwnd))
        if existing is None:_overlays[int(hwnd)]=dict(api=_u,capture_excluded=bool(capture_excluded))
        else:existing.update(api=_u,capture_excluded=bool(capture_excluded))


def unregister_overlay(hwnd):
    with _lock:_overlays.pop(int(hwnd),None)


def configure_overlay(hwnd,*,passive=False):
    """Reapply topmost without activation and confirm capture exclusion."""
    style=_u.GetWindowLongPtrW(hwnd,-20)
    requested=style|0x08000000|0x80 # NOACTIVATE, TOOLWINDOW
    requested=(requested|0x80000|0x20) if passive else (requested & ~0x20)
    _u.SetWindowLongPtrW(hwnd,-20,requested)
    actual=_u.GetWindowLongPtrW(hwnd,-20)
    if actual & (0x08000080|0x20) != requested & (0x08000080|0x20):
        unregister_overlay(hwnd)
        raise OSError('Overlay input window policy unavailable')
    if passive and not actual & 0x80000:
        unregister_overlay(hwnd)
        raise OSError('Overlay layered input pass-through unavailable')
    affinity=W.DWORD()
    excluded=bool(_u.SetWindowDisplayAffinity(hwnd,0x11)
        and _u.GetWindowDisplayAffinity(hwnd,C.byref(affinity)) and affinity.value==0x11)
    register_overlay(hwnd,capture_excluded=excluded)
    if not _u.SetWindowPos(hwnd,-1,0,0,0,0,0x13): # TOPMOST, NOMOVE|NOSIZE|NOACTIVATE
        unregister_overlay(hwnd)
        raise OSError('Overlay topmost window policy unavailable')
    return dict(hwnd=int(hwnd),passive_input=bool(passive),capture_excluded=excluded,
                capture_fallback='none' if excluded else 'hide_during_capture')


@contextmanager
def capture_scope():
    """Hide only unexcluded visible overlays, then restore without activation."""
    # UI policy updates must never wait for worker ShowWindow messages while
    # holding the same lock. Only capture workers serialize the full scope.
    with _capture_lock:
        with _lock:records=tuple(_overlays.items())
        hidden=[]
        try:
            for hwnd,record in records:
                api=record['api']
                if not api.IsWindow(hwnd):
                    unregister_overlay(hwnd);continue
                if record['capture_excluded'] or not api.IsWindowVisible(hwnd):continue
                api.ShowWindow(hwnd,0)
                if api.IsWindowVisible(hwnd):raise OSError('Cannot hide overlay before capture')
                hidden.append((hwnd,record))
            if hidden:
                # Wait for desktop composition to observe the hidden windows.
                try:C.WinDLL('dwmapi').DwmFlush()
                except (AttributeError,OSError):pass
            yield
        finally:
            for hwnd,record in hidden:
                api=record['api']
                with _lock:registered=_overlays.get(hwnd) is record
                if registered and api.IsWindow(hwnd):
                    api.ShowWindow(hwnd,4) # SW_SHOWNOACTIVATE
                    with _lock:still_registered=_overlays.get(hwnd) is record
                    if not still_registered:api.ShowWindow(hwnd,0)
