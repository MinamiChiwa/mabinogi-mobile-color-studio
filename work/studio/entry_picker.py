"""Pick a client-relative dye-entry point from a frozen desktop image."""
import tkinter as tk
import threading
import time
from PIL import ImageGrab, ImageTk
import platform_win
from window_target import resolve_target
from i18n import tr
from screen_mapping import screen_point


def client_point(screen_point, geometry):
    """Convert an absolute screen point to a bounded client-relative point."""
    left, top, width, height = map(int, geometry)
    x, y = map(int, screen_point)
    point = (x-left, y-top)
    if width <= 0 or height <= 0 or not (0 <= point[0] < width and 0 <= point[1] < height):
        raise ValueError('Select a point inside the game window.')
    return point


def validate_entry_geometry(point, expected_size, geometry):
    """Reject an entry recorded against a different client size or outside it."""
    _, _, width, height = map(int, geometry)
    expected_width, expected_height = map(int, expected_size)
    if (width, height) != (expected_width, expected_height):
        raise ValueError('游戏窗口尺寸已变化，请重新设置染色入口位置。')
    x, y = map(int, point)
    if width <= 0 or height <= 0 or not (0 <= x < width and 0 <= y < height):
        raise ValueError('染色入口位置已超出游戏窗口，请重新设置。')
    return (width, height)


def pick_game_entry(root, target, callback):
    """Let the user mark a button on a frozen screenshot; sends no game input."""
    if getattr(root, 'picking', False) or getattr(root, 'busy', False):
        return False
    root.picking = True
    try:
        target = resolve_target(target)
        game = platform_win.Game(threading.Event(), target=target)
        game.geometry()  # Reject a minimized window before attempting to focus it.
        game.focus()
        geometry = game.geometry()
        root.withdraw()
        time.sleep(.18)
        screenshot = ImageGrab.grab(all_screens=True).convert('RGB')
    except Exception as exc:
        root.picking = False
        root.deiconify()
        root.status.configure(text=tr(str(exc)))
        return False

    x0 = platform_win.u.GetSystemMetrics(76)
    y0 = platform_win.u.GetSystemMetrics(77)

    try:
        overlay = tk.Toplevel(root)
        overlay.title(tr('设置染色入口位置'))
        overlay.attributes('-fullscreen', True)
        overlay.attributes('-topmost', True)
        overlay.geometry(f'{screenshot.width}x{screenshot.height}+0+0')
        canvas = tk.Canvas(overlay, highlightthickness=0, cursor='crosshair')
        canvas.pack(fill='both', expand=True)
        photo = ImageTk.PhotoImage(screenshot)
        canvas.create_image(0, 0, image=photo, anchor='nw')
        overlay.photo = photo
        label = tk.Label(overlay, text=tr('冻结画面：单击普通染色入口位置；Esc 取消'),
                         bg='#10151F', fg='white', font=('Microsoft YaHei UI', 12),
                         padx=14, pady=10)
        label.place(x=20, y=20)

        def finish(point=None):
            overlay.destroy()
            root.picking = False
            root.deiconify()
            root.lift()
            if point is not None:
                callback(target, point, (geometry[2], geometry[3]))

        def point_at(event):
            absolute=screen_point(event.x,event.y,
                                 (canvas.winfo_width(),canvas.winfo_height()),
                                 screenshot.size,(x0,y0))
            return client_point(absolute, geometry)

        def preview(event):
            try:
                x, y = point_at(event)
                label.configure(text=tr(f'客户区坐标 ({x}, {y}) · 单击设置 / Esc 取消'),
                                 bg='#10151F', fg='white')
            except ValueError:
                label.configure(text=tr('请在游戏窗口内选择 · Esc 取消'),
                                 bg='#7A3434', fg='white')
            label.place(x=min(max(0,event.x+20),max(0,screenshot.width-430)),
                        y=min(max(0,event.y+20),max(0,screenshot.height-60)))

        def choose(event):
            try:
                point = point_at(event)
            except ValueError:
                preview(event)
                return
            try:
                if tuple(game.geometry()) != tuple(geometry):
                    finish()
                    root.status.configure(text=tr('游戏窗口位置或尺寸已变化，请重新设置染色入口位置。'))
                    return
            except Exception:
                finish()
                root.status.configure(text=tr('游戏窗口位置或尺寸已变化，请重新设置染色入口位置。'))
                return
            finish(point)

        canvas.bind('<Motion>', preview)
        canvas.bind('<Button-1>', choose)
        overlay.bind('<Escape>', lambda _event: finish())
        overlay.bind('<Button-3>', lambda _event: finish())
        overlay.update_idletasks()
        hwnd = platform_win.u.GetParent(overlay.winfo_id()) or overlay.winfo_id()
        platform_win.u.SetWindowPos(hwnd, -1, x0, y0, screenshot.width, screenshot.height, 0x0040)
        overlay.focus_force()
        return True
    except Exception as exc:
        root.picking = False
        root.deiconify()
        root.status.configure(text=tr(f'染色入口选择失败：{exc}'))
        return False
