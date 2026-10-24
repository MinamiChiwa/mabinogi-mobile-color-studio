"""Eyedropper regressions without game input or desktop interaction."""
import ctypes
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image
import eyedropper
import eyedropper_native as native


def context_value(value):
    value = value.value if isinstance(value, ctypes.c_void_p) else value
    return value - (1 << 64) if value is not None and value >= (1 << 63) else value


class DesktopAPI:
    def __init__(self, bbox=(0, 0, 2560, 1440), cursor=(1800, 700)):
        self.bbox = bbox
        self.cursor = cursor
        self.context = -2
        self.positioned = []
        self.metrics_contexts = []
        self.cursor_contexts = []
        self.foreign = False
        self.window_context = -4
        self.failed_capture_context = False
        self.resized_client = False
        self.key_down = False
        self.focus_requests = []

    def SetThreadDpiAwarenessContext(self, value):
        if context_value(value) == -4 and self.failed_capture_context:
            return None
        previous = self.context
        self.context = context_value(value)
        return previous

    def GetThreadDpiAwarenessContext(self):
        return self.context

    def AreDpiAwarenessContextsEqual(self, a, b):
        return context_value(a) == context_value(b)

    def GetWindowDpiAwarenessContext(self, hwnd):
        return self.window_context

    def GetSystemMetrics(self, index):
        self.metrics_contexts.append(self.context)
        l, t, r, b = self.bbox
        return {76: l, 77: t, 78: r-l, 79: b-t}[index]

    def GetCursorPos(self, pointer):
        self.cursor_contexts.append(self.context)
        pointer._obj.x, pointer._obj.y = self.cursor
        return True

    def GetAsyncKeyState(self, key):
        return -32768 if self.key_down else 0

    def GetParent(self, hwnd):
        # GetParent is unsafe: an owned top-level can report another window.
        return 999

    def GetAncestor(self, hwnd, kind):
        return 102

    def IsWindow(self, hwnd):
        return True

    def GetWindowThreadProcessId(self, hwnd, pointer):
        if pointer is not None:
            pointer._obj.value = os.getpid()+1 if self.foreign else os.getpid()
        return 1

    def GetClassNameW(self, hwnd, buffer, count):
        buffer.value = 'UnityWndClass' if self.foreign else 'TkTopLevel'
        return len(buffer.value)

    def SetWindowPos(self, hwnd, after, x, y, w, h, flags):
        self.positioned.append((hwnd, after, x, y, w, h, flags, self.context))
        return True

    def GetClientRect(self, hwnd, pointer):
        l, t, r, b = self.bbox
        pointer._obj.left = pointer._obj.top = 0
        pointer._obj.right, pointer._obj.bottom = (r-l)//2 if self.resized_client else r-l, b-t
        return True

    def ClientToScreen(self, hwnd, pointer):
        pointer._obj.x += self.bbox[0]
        pointer._obj.y += self.bbox[1]
        return True


class Widget:
    def __init__(self, *args, **kwargs):
        self.bindings = {}
        self.config = kwargs
        self.exists = True
        self.attributes_seen = []
        self.photo = None
        self.scheduled = []

    def configure(self, **kwargs): self.config.update(kwargs)
    def pack(self, **kwargs): pass
    def place(self, **kwargs): pass
    def create_image(self, *args, **kwargs): self.image = kwargs['image']
    def bind(self, event, callback): self.bindings[event] = callback
    def title(self, value): self.window_title = value
    def attributes(self, *args): self.attributes_seen.append(args)
    def geometry(self, value): self.geometry_value = value
    def overrideredirect(self, value): self.borderless = value
    def withdraw(self): self.hidden = True
    def deiconify(self): self.hidden = False
    def lift(self): pass
    def update_idletasks(self): pass
    def destroy(self): self.exists = False
    def winfo_id(self): return 101
    def winfo_exists(self): return self.exists
    def winfo_width(self): return 1280
    def winfo_height(self): return 720
    def focus_force(self): self.focus_requested = True
    def after(self, delay, callback):
        self.scheduled.append(callback)
        return 'overlay-timer'
    def after_cancel(self, timer): pass
    def protocol(self, *args): pass


class Root(Widget):
    def __init__(self):
        super().__init__()
        self.busy = False
        self.picking = False
        self.status = Widget()
        self.scheduled = []

    def after(self, delay, callback):
        self.scheduled.append(callback)
        return 'root-timer'


class EyedropperTests(unittest.TestCase):
    def run_picker(self, api, *, wrong_size=False):
        root = Root()
        overlay, canvas, label = Widget(), Widget(), Widget()
        canvas.preview_label = label
        chosen, captures = [], []
        l, t, r, b = api.bbox
        screen = Image.new('RGB', (r-l-int(wrong_size), b-t))
        screen.putpixel((api.cursor[0]-l, api.cursor[1]-t), (17, 91, 203))

        def grab(**kwargs):
            captures.append((kwargs, api.context))
            return screen

        patches = [patch.object(native, '_u', api),
            patch.object(eyedropper.tk, 'Toplevel', return_value=overlay),
            patch.object(eyedropper.tk, 'Canvas', return_value=canvas),
            patch.object(eyedropper.tk, 'Label', return_value=label),
            patch.object(eyedropper.ImageGrab, 'grab', side_effect=grab),
            patch.object(eyedropper.ImageTk, 'PhotoImage', side_effect=lambda image, **_: image),
            patch.object(native, 'configure_overlay', return_value={}),
            patch.object(native, 'unregister_overlay')]
        from contextlib import ExitStack
        with ExitStack() as stack:
            for context in patches: stack.enter_context(context)
            eyedropper.pick_screen(root, chosen.append)
            root.scheduled.pop(0)()
            yield root, overlay, canvas, chosen, captures

    def test_capture_and_desktop_bounds_use_same_physical_context(self):
        api = DesktopAPI(bbox=(-3840, -120, 2560, 2160), cursor=(-40, 700))
        for root, overlay, canvas, chosen, captures in self.run_picker(api):
            self.assertEqual(captures, [({'all_screens': True}, -4)])
            self.assertEqual(api.metrics_contexts, [-4]*4)
            self.assertEqual(api.context, -2)

    def test_click_samples_physical_cursor_at_2560_and_4k_with_negative_origin(self):
        for bbox, cursor in [((0, 0, 2560, 1440), (1800, 700)),
                             ((-3840, -120, 0, 2040), (-40, 700))]:
            with self.subTest(bbox=bbox):
                api = DesktopAPI(bbox, cursor)
                for root, overlay, canvas, chosen, captures in self.run_picker(api):
                    # Tk event/canvas units deliberately differ from the frozen bitmap.
                    result = canvas.bindings['<Button-1>'](SimpleNamespace(x=400, y=200))
                    self.assertEqual(chosen, ['#115BCB'])
                    self.assertEqual(result, 'break')
                    self.assertEqual(api.cursor_contexts[-1], -4)
                    self.assertEqual(api.context, -2)

    def test_picker_positions_only_validated_tk_root_without_activation(self):
        api = DesktopAPI()
        for root, overlay, canvas, chosen, captures in self.run_picker(api):
            self.assertFalse(getattr(overlay, 'focus_requested', False))
            self.assertNotIn(('-fullscreen', True), overlay.attributes_seen)
            self.assertTrue(api.positioned)
            for hwnd, after, x, y, w, h, flags, context in api.positioned:
                self.assertEqual(hwnd, 102)
                self.assertTrue(flags & 0x10)  # SWP_NOACTIVATE
                self.assertEqual(context, -4)

    def test_foreign_native_window_is_rejected_before_any_window_move(self):
        api = DesktopAPI(); api.foreign = True
        for root, overlay, canvas, chosen, captures in self.run_picker(api):
            self.assertEqual(api.positioned, [])
            self.assertFalse(root.picking)
            self.assertFalse(overlay.exists)
            self.assertEqual(chosen, [])

    def test_capture_size_mismatch_stops_instead_of_stretching_pixels(self):
        api = DesktopAPI()
        for root, overlay, canvas, chosen, captures in self.run_picker(api, wrong_size=True):
            self.assertFalse(root.picking)
            self.assertEqual(api.positioned, [])
            self.assertEqual(chosen, [])

    def test_failed_physical_context_never_captures(self):
        api = DesktopAPI(); api.failed_capture_context = True
        for root, overlay, canvas, chosen, captures in self.run_picker(api):
            self.assertEqual(captures, [])
            self.assertEqual(api.positioned, [])
            self.assertFalse(root.picking)

    def test_scaled_native_window_is_rejected_before_move(self):
        api = DesktopAPI(); api.window_context = -2
        for root, overlay, canvas, chosen, captures in self.run_picker(api):
            self.assertEqual(api.positioned, [])
            self.assertFalse(root.picking)

    def test_native_extent_mismatch_cleans_up_picker(self):
        api = DesktopAPI(); api.resized_client = True
        for root, overlay, canvas, chosen, captures in self.run_picker(api):
            self.assertFalse(overlay.exists)
            self.assertFalse(root.picking)
            self.assertEqual(chosen, [])

    def test_escape_poll_cancels_without_keyboard_focus(self):
        api = DesktopAPI()
        for root, overlay, canvas, chosen, captures in self.run_picker(api):
            api.key_down = True
            overlay.scheduled.pop(0)()
            self.assertFalse(overlay.exists)
            self.assertFalse(root.picking)
            self.assertEqual(chosen, [])

    def test_busy_run_does_not_open_picker(self):
        root = Root(); root.busy = True
        eyedropper.pick_screen(root, lambda _: self.fail('Unexpected color'))
        self.assertEqual(root.scheduled, [])
        self.assertFalse(root.picking)

    def test_preview_label_click_picks_the_pixel_behind_it(self):
        api = DesktopAPI(cursor=(2550, 1430))
        for root, overlay, canvas, chosen, captures in self.run_picker(api):
            result = canvas.preview_label.bindings.get('<Button-1>', lambda _: None)(
                SimpleNamespace(x=20, y=15))
            self.assertEqual(chosen, ['#115BCB'])
            self.assertEqual(result, 'break')


if __name__ == '__main__':
    unittest.main()
