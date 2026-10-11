"""Frozen desktop eyedropper with one physical pixel per sampled image pixel."""
import tkinter as tk
from PIL import ImageGrab, ImageTk

from i18n import tr
import eyedropper_native as native
from screen_mapping import frozen_image_point
from window_dpi import physical_pixel_context


def pixel_hex(image, x, y):
    x = max(0, min(image.width-1, int(x)))
    y = max(0, min(image.height-1, int(y)))
    return '#%02X%02X%02X' % image.convert('RGB').getpixel((x, y))


def pick_screen(root, callback):
    if getattr(root, 'picking', False) or root.busy:
        return
    root.picking = True
    root.withdraw()

    def open_overlay():
        overlay = None
        hwnd = None
        timer = None
        finished = False

        def finish(color=None, error=None):
            nonlocal finished, timer
            if finished:
                return 'break'
            finished = True
            if timer is not None:
                overlay.after_cancel(timer)
                timer = None
            if hwnd is not None:
                native.unregister_overlay(hwnd)
            if overlay is not None:
                overlay.destroy()
            root.picking = False
            root.deiconify()
            root.lift()
            if error is not None:
                root.status.configure(text=tr('屏幕取色失败：') + tr(str(error)))
            elif color is not None:
                callback(color)
            return 'break'

        try:
            bounds = native.desktop_bounds()
            with physical_pixel_context(native._u):
                screen = ImageGrab.grab(all_screens=True).convert('RGB')
            if screen.size != (bounds[2]-bounds[0], bounds[3]-bounds[1]):
                raise OSError('屏幕尺寸已变化，请重新取色。')

            # Create this window in physical units without changing the CTk root.
            with physical_pixel_context(native._u):
                overlay = tk.Toplevel(root)
                overlay.withdraw()
                overlay.title(tr('屏幕吸管 · 单击取色 / Esc 取消'))
                overlay.overrideredirect(True)
                overlay.geometry(f'{screen.width}x{screen.height}+0+0')
                canvas = tk.Canvas(overlay, highlightthickness=0, borderwidth=0, cursor='crosshair')
                canvas.pack(fill='both', expand=True)
                photo = ImageTk.PhotoImage(screen, master=overlay)
                canvas.create_image(0, 0, image=photo, anchor='nw')
                overlay.photo = photo
                label = tk.Label(overlay, text=tr('移动预览 · 单击取色 · Esc 取消'),
                    bg='#10151F', fg='white', font=('Microsoft YaHei UI', 12), padx=14, pady=10)
                label.place(x=20, y=20)
                overlay.update_idletasks()

            def point_at_cursor():
                return frozen_image_point(*native.physical_cursor(), bounds[:2], screen.size)

            def preview(_event=None):
                try:
                    x, y = point_at_cursor()
                    color = pixel_hex(screen, x, y)
                    label.configure(text=tr(f'{color}   单击取色 · Esc 取消'), bg=color,
                        fg='black' if sum(int(color[i:i+2], 16) for i in (1, 3, 5)) > 400 else 'white')
                    label.place(x=min(x+20, max(0, screen.width-320)),
                                y=min(y+20, max(0, screen.height-60)))
                except Exception as exc:
                    finish(error=exc)

            def choose(_event):
                try:
                    color = pixel_hex(screen, *point_at_cursor())
                except Exception as exc:
                    return finish(error=exc)
                return finish(color=color)

            canvas.bind('<Motion>', preview)
            canvas.bind('<Button-1>', choose)
            label.bind('<Motion>', preview)
            label.bind('<Button-1>', choose)
            # A child click must stop before CTk's bind_all focus handler.
            overlay.bind('<Button-1>', lambda _event: 'break')
            overlay.bind('<Escape>', lambda _event: finish())
            overlay.bind('<Button-3>', lambda _event: finish())
            overlay.protocol('WM_DELETE_WINDOW', finish)
            hwnd = native.show_picker(overlay, bounds)

            def check_cancel():
                nonlocal timer
                timer = None
                if finished:
                    return
                if native.escape_pressed():
                    finish()
                else:
                    timer = overlay.after(30, check_cancel)

            timer = overlay.after(30, check_cancel)
        except Exception as exc:
            finish(error=exc)

    root.after(180, open_overlay)
