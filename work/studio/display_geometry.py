"""Physical monitor work areas and logical CTk sizes, without game input."""
import ctypes as C
from ctypes import wintypes as W


class _MonitorInfo(C.Structure):
    _fields_ = [('cbSize', W.DWORD), ('rcMonitor', W.RECT),
                ('rcWork', W.RECT), ('dwFlags', W.DWORD)]


def work_area(window, position=None):
    """Use the nearest actual monitor, excluding its taskbar and desktop gaps."""
    try:
        user = C.windll.user32
        user.MonitorFromWindow.argtypes = [W.HWND, W.DWORD]
        user.MonitorFromWindow.restype = W.HANDLE
        user.MonitorFromRect.argtypes = [C.POINTER(W.RECT), W.DWORD]
        user.MonitorFromRect.restype = W.HANDLE
        user.GetMonitorInfoW.argtypes = [W.HANDLE, C.POINTER(_MonitorInfo)]
        user.GetMonitorInfoW.restype = W.BOOL
        if position is None:
            handle = user.MonitorFromWindow(window.winfo_id(), 2)
        else:
            x, y = map(int, position)
            rect = W.RECT(x, y, x + 1, y + 1)
            handle = user.MonitorFromRect(C.byref(rect), 2)
        info = _MonitorInfo(); info.cbSize = C.sizeof(info)
        if handle and user.GetMonitorInfoW(handle, C.byref(info)):
            rect = info.rcWork
            return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
    except (AttributeError, OSError):
        pass
    return 0, 0, window.winfo_screenwidth(), window.winfo_screenheight()


def logical_size(window, preferred, margins=(80, 100), reference=None):
    """Fit logical CTk dimensions into a physical monitor work area."""
    _, _, width, height = work_area(reference if reference is not None else window)
    scale = max(.1, float(window._get_window_scaling()))
    available = (max(1, int(width / scale) - int(margins[0])),
                 max(1, int(height / scale) - int(margins[1])))
    return tuple(min(int(wanted), limit) for wanted, limit in zip(preferred, available))


def clamp_position(position, rect, size):
    """Clamp physical coordinates, retaining negative monitor origins."""
    left, top, width, height = map(int, rect)
    return (min(max(left, int(position[0])), left + max(0, width - int(size[0]))),
            min(max(top, int(position[1])), top + max(0, height - int(size[1]))))
