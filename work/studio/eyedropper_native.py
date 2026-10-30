"""Physical desktop coordinates, cursor and Esc polling for the screen eyedropper."""
import ctypes as C
from ctypes import wintypes as W

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
