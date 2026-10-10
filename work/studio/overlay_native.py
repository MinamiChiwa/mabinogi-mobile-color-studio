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
    ('GetWindowThreadProcessId',[W.HWND,C.POINTER(W.DWORD)],W.DWORD),
    ('IsWindow',[W.HWND],W.BOOL),('IsWindowVisible',[W.HWND],W.BOOL),
    ('ShowWindow',[W.HWND,C.c_int],W.BOOL)):
    function=getattr(_u,name);function.argtypes=args;function.restype=result
_lock=threading.RLock()
_capture_lock=threading.RLock()
_overlays={}
_subclasses={}
_subclass_id=0x43534F56
_subclass_callback_type=C.WINFUNCTYPE(C.c_ssize_t,W.HWND,W.UINT,W.WPARAM,W.LPARAM,C.c_size_t,C.c_size_t)
_comctl=C.WinDLL('comctl32',use_last_error=True)
for name,args,result in (
    ('SetWindowSubclass',[W.HWND,_subclass_callback_type,C.c_size_t,C.c_size_t],W.BOOL),
    ('RemoveWindowSubclass',[W.HWND,_subclass_callback_type,C.c_size_t],W.BOOL),
    ('DefSubclassProc',[W.HWND,W.UINT,W.WPARAM,W.LPARAM],C.c_ssize_t)):
    function=getattr(_comctl,name);function.argtypes=args;function.restype=result


@_subclass_callback_type
def _noactivate_subclass(hwnd,message,wparam,lparam,subclass_id,reference):
    # Keep this callback strongly referenced at module scope, including while
    # WM_NCDESTROY is running. Tk retains its original window procedure.
    if message==0x21:return 3 # WM_MOUSEACTIVATE -> MA_NOACTIVATE, deliver click
    if message==0x82: # WM_NCDESTROY
        _comctl.RemoveWindowSubclass(hwnd,_noactivate_subclass,subclass_id)
        with _lock:
            _subclasses.pop(int(hwnd),None);_overlays.pop(int(hwnd),None)
    return _comctl.DefSubclassProc(hwnd,message,wparam,lparam)


def _ensure_noactivation(hwnd):
    with _lock:installed=int(hwnd) in _subclasses
    if installed:return
    owner=int(_u.GetWindowThreadProcessId(hwnd,None))
    if owner!=threading.get_native_id():raise OSError('Overlay activation policy requires its UI thread')
    if not _comctl.SetWindowSubclass(hwnd,_noactivate_subclass,_subclass_id,0):
        raise OSError('Overlay mouse activation policy unavailable')
    with _lock:_subclasses[int(hwnd)]=owner


def _remove_noactivation(hwnd):
    with _lock:owner=_subclasses.get(int(hwnd))
    # A worker can invalidate registration, but cross-thread subclass removal
    # is unsupported. The UI thread or WM_NCDESTROY removes it later.
    if owner!=threading.get_native_id():return
    if _u.IsWindow(hwnd) and not _comctl.RemoveWindowSubclass(hwnd,_noactivate_subclass,_subclass_id):return
    with _lock:_subclasses.pop(int(hwnd),None)


def register_overlay(hwnd,*,capture_excluded):
    with _lock:
        existing=_overlays.get(int(hwnd))
        if existing is None:_overlays[int(hwnd)]=dict(api=_u,capture_excluded=bool(capture_excluded))
        else:existing.update(api=_u,capture_excluded=bool(capture_excluded))


def unregister_overlay(hwnd):
    with _lock:_overlays.pop(int(hwnd),None)
    _remove_noactivation(hwnd)


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
    try:_ensure_noactivation(hwnd)
    except OSError:
        unregister_overlay(hwnd);raise
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
def _hidden_overlays(*,for_input):
    """Serialize suppression without holding the registry lock across Win32 calls."""
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
                if (not for_input and record['capture_excluded']) or not api.IsWindowVisible(hwnd):continue
                api.ShowWindow(hwnd,0)
                if api.IsWindowVisible(hwnd):raise OSError('Cannot hide overlay before input' if for_input else 'Cannot hide overlay before capture')
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


@contextmanager
def capture_scope():
    """Hide unexcluded visible overlays only for capture; preserve affinity support."""
    with _hidden_overlays(for_input=False):yield


@contextmanager
def input_scope():
    """Hide registered visible overlays for one gesture, restoring without focus."""
    with _hidden_overlays(for_input=True):yield
