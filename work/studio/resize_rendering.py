"""Reduce redundant full-window redraws during native Windows resizing."""

import ctypes
import sys
from ctypes import wintypes


GCL_STYLE = -26
CS_VREDRAW = 0x0001
CS_HREDRAW = 0x0002
RESIZE_REDRAW_FLAGS = CS_HREDRAW | CS_VREDRAW
GA_ROOT = 2


class TopLevelResizeRedrawOptimization:
    """Temporarily remove Tk's class-wide redraw-on-size flags.

    Tk's top-level class uses CS_HREDRAW/CS_VREDRAW, which invalidates the
    whole window on every horizontal/vertical size change. The UI keeps its
    children at fixed sizes, so only newly exposed pixels need repainting.
    The class flags are restored before the application exits.
    """

    def __init__(self, user32=None, platform=None):
        self._user32 = user32
        self._platform = sys.platform if platform is None else platform
        self._hwnd = None
        self._removed_flags = 0

    def _api(self):
        if self._platform != "win32":
            return None
        if self._user32 is None:
            try:
                self._user32 = ctypes.windll.user32
            except AttributeError:
                return None

        api = self._user32
        getter = getattr(api, "GetClassLongPtrW", None) or getattr(api, "GetClassLongW", None)
        setter = getattr(api, "SetClassLongPtrW", None) or getattr(api, "SetClassLongW", None)
        if getter is None or setter is None:
            return None
        try:
            getter.argtypes = [wintypes.HWND, ctypes.c_int]
            getter.restype = ctypes.c_size_t
            setter.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_size_t]
            setter.restype = ctypes.c_size_t
            ancestor = getattr(api, "GetAncestor", None)
            if ancestor is not None:
                ancestor.argtypes = [wintypes.HWND, wintypes.UINT]
                ancestor.restype = wintypes.HWND
        except (AttributeError, TypeError):
            # Python fakes used by tests need not accept ctypes signatures.
            pass
        return getter, setter, getattr(api, "GetAncestor", None)

    def disable_for(self, hwnd):
        """Disable full redraw flags for the Tk top-level class, if present."""
        if not hwnd or self._hwnd is not None:
            return False
        api = self._api()
        if api is None:
            return False
        getter, setter, ancestor = api
        top_level = ancestor(hwnd, GA_ROOT) if ancestor is not None else hwnd
        top_level = top_level or hwnd
        style = getter(top_level, GCL_STYLE)
        removed = style & RESIZE_REDRAW_FLAGS
        if not removed:
            return False

        setter(top_level, GCL_STYLE, style & ~RESIZE_REDRAW_FLAGS)
        if getter(top_level, GCL_STYLE) & removed:
            return False
        self._hwnd = top_level
        self._removed_flags = removed
        return True

    def restore(self):
        """Restore the original redraw bits without overwriting other changes."""
        if self._hwnd is None:
            return False
        api = self._api()
        if api is None:
            return False
        getter, setter, _ancestor = api
        current = getter(self._hwnd, GCL_STYLE)
        setter(self._hwnd, GCL_STYLE, current | self._removed_flags)
        restored = getter(self._hwnd, GCL_STYLE)
        if restored & self._removed_flags != self._removed_flags:
            return False
        self._hwnd = None
        self._removed_flags = 0
        return True
