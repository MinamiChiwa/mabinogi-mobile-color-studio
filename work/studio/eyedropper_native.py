"""Physical desktop coordinates and a verified, nonactivating Tk picker window."""
import ctypes as C
from ctypes import wintypes as W
import os

from overlay_native import configure_overlay, unregister_overlay
from window_dpi import physical_pixel_context


_u = C.WinDLL('user32', use_last_error=True)
for name, args, result in (
    ('SetThreadDpiAwarenessContext', [C.c_void_p], C.c_void_p),
    ('GetThreadDpiAwarenessContext', [], C.c_void_p),
    ('AreDpiAwarenessContextsEqual', [C.c_void_p, C.c_void_p], W.BOOL),
    ('GetWindowDpiAwarenessContext', [W.HWND], C.c_void_p),
    ('GetSystemMetrics', [C.c_int], C.c_int),
    ('GetCursorPos', [C.POINTER(W.POINT)], W.BOOL),
    ('GetAsyncKeyState', [C.c_int], C.c_short),
    ('GetAncestor', [W.HWND, W.UINT], W.HWND),
    ('GetWindowThreadProcessId', [W.HWND, C.POINTER(W.DWORD)], W.DWORD),
    ('GetClassNameW', [W.HWND, W.LPWSTR, C.c_int], C.c_int),
    ('IsWindow', [W.HWND], W.BOOL),
    ('GetClientRect', [W.HWND, C.POINTER(W.RECT)], W.BOOL),
    ('ClientToScreen', [W.HWND, C.POINTER(W.POINT)], W.BOOL),
    ('SetWindowPos', [W.HWND, W.HWND, C.c_int, C.c_int, C.c_int, C.c_int, W.UINT], W.BOOL),
):
    function = getattr(_u, name)
    function.argtypes = args
    function.restype = result


def desktop_bounds():
    """Read one physical virtual-desktop rectangle, including negative origins."""
    with physical_pixel_context(_u):
        left, top, width, height = (_u.GetSystemMetrics(index) for index in (76, 77, 78, 79))
    if width <= 0 or height <= 0:
        raise OSError('无法读取屏幕物理边界，请重试。')
    return left, top, left+width, top+height


def physical_cursor():
    with physical_pixel_context(_u):
        point = W.POINT()
        if not _u.GetCursorPos(C.byref(point)):
            raise OSError('无法读取鼠标物理坐标，请重试。')
    return point.x, point.y


def escape_pressed():
    return bool(_u.GetAsyncKeyState(0x1B) & 0x8000)


def picker_hwnd(window):
    """Never position an owner or any foreign window returned by a bad handle."""
    hwnd = _u.GetAncestor(window.winfo_id(), 2)  # GA_ROOT, excludes owner chains.
    pid = W.DWORD()
    class_name = C.create_unicode_buffer(256)
    if (not hwnd or not _u.IsWindow(hwnd)
            or not _u.GetWindowThreadProcessId(hwnd, C.byref(pid))
            or pid.value != os.getpid()
            or not _u.GetClassNameW(hwnd, class_name, len(class_name))
            or class_name.value != 'TkTopLevel'
            or not _u.AreDpiAwarenessContextsEqual(
                _u.GetWindowDpiAwarenessContext(hwnd), C.c_void_p(-4))):
        raise OSError('无法确认取色窗口，请重试。')
    return int(hwnd)


def show_picker(window, bounds):
    """Show only the confirmed picker at 1:1 physical pixels without activation."""
    hwnd = picker_hwnd(window)
    left, top, right, bottom = bounds
    try:
        with physical_pixel_context(_u):
            configure_overlay(hwnd, passive=False)
            if not _u.SetWindowPos(hwnd, -1, left, top, right-left, bottom-top, 0x50):
                raise OSError('无法显示取色窗口，请重试。')  # SHOWWINDOW | NOACTIVATE
            rect, origin = W.RECT(), W.POINT()
            if (not _u.GetClientRect(hwnd, C.byref(rect))
                    or not _u.ClientToScreen(hwnd, C.byref(origin))
                    or (origin.x, origin.y, origin.x+rect.right, origin.y+rect.bottom) != tuple(bounds)):
                raise OSError('取色窗口与屏幕像素不一致，请重试。')
        return hwnd
    except Exception:
        unregister_overlay(hwnd)
        raise
