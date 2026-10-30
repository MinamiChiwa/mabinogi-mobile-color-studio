"""Qt 屏幕吸管：冻结整屏 → 十字光标取色 → 单击确认 / Esc 取消。

## 适用范围

* **平台**：仅 Windows（依赖 `GetSystemMetrics` / `GetCursorPos` 的物理像素语义、
  `SetThreadDpiAwarenessContext` 的 PMv2 上下文）。macOS / Linux 不适用。
* **屏幕**：支持多显示器与负坐标虚拟桌面；整块虚拟桌面冻结成一张位图。
  混合 DPI 的多屏按**主屏 DPR** 换算窗口尺寸，几何一致性由
  `GetClientRect` + `ClientToScreen` 实测校验兜底（不一致即报错而非取错色）。
* **取色范围**：屏幕上**任意位置**，包括其他应用窗口、全屏游戏画面、任务栏。
  取的是冻结瞬间的像素，取色过程中画面变化不影响结果。
* **精度**：**物理像素级**。全程在 PMv2 物理像素上下文里读坐标与截图，
  不经过任何 UI 缩放换算，因此 125% / 150% 缩放下也能命中单个物理像素。
* **不抢焦点**：窗口注册 `WS_EX_NOACTIVATE`，取色期间原前台窗口保持前台，
  不会打断全屏游戏。

## 调用方式

主界面（区域卡「⌖ 吸管」按钮）::

    bridge.eyedropper(cardIndex)  →  QtHost.pick_color(callback)

程序内直接调用::

    host.pick_color(lambda hex_value: ...)     # hex_value 形如 '#A3122E'
    host.pick_color_for(card)                  # 写回该卡的目标色

取消（Esc / 右键 / 关窗）时不回调，`host.picking` 复位。

## 依赖

坐标映射、DPI 上下文、桌面边界与按键轮询来自
`eyedropper_native` / `screen_mapping` / `window_dpi`；
窗口的校验与定位由本模块的 `_show_picker()` 完成。
"""
from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W

from PIL import ImageGrab
from PySide6.QtCore import QObject, Slot, QTimer, QUrl
from PySide6.QtGui import QImage
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickImageProvider


def pixel_hex(image, x, y):
    """读一个物理像素的 HEX；坐标越界时夹到图像边缘。"""
    x = max(0, min(image.width - 1, int(x)))
    y = max(0, min(image.height - 1, int(y)))
    return '#%02X%02X%02X' % image.convert('RGB').getpixel((x, y))

import eyedropper_native as native
from i18n import tr
from screen_mapping import frozen_image_point
from window_dpi import physical_pixel_context

_UNUSED = (C, W)  # 保持与原生模块一致的导入，便于将来扩展

_QML_DIR = None


def _qml_dir():
    global _QML_DIR
    if _QML_DIR is None:
        from pathlib import Path
        _QML_DIR = Path(__file__).resolve().parent / 'qml'
    return _QML_DIR


class FrozenProvider(QQuickImageProvider):
    """把冻结截图交给 QML。

    用 ImageProvider 而不是 data URI：整屏位图转 base64 会产生数 MB 字符串，
    首帧明显卡顿；这里直接把 QImage 交给纹理上传。
    """

    def __init__(self):
        super().__init__(QQuickImageProvider.ImageType.Image)
        self._image = None

    def set_image(self, image):
        self._image = image

    def requestImage(self, _id, size, requested):
        if self._image is None:
            return QImage(), requested
        image = self._image
        if size is not None:
            size.setWidth(image.width())
            size.setHeight(image.height())
        return image


def _pil_to_qimage(image):
    if image.mode != 'RGB':
        image = image.convert('RGB')
    data = image.tobytes('raw', 'RGB')
    return QImage(data, image.width, image.height, image.width * 3,
                  QImage.Format.Format_RGB888).copy()


class QtEyedropper(QObject):
    """一次取色会话。每次调用 ``pick_screen()`` 新建一个实例。"""

    def __init__(self, host, callback, parent=None):
        super().__init__(parent)
        self._host = host
        self._callback = callback
        self._engine = None
        self._window = None
        self._provider = FrozenProvider()
        self._image = None
        self._bounds = None
        self._dpr = 1.0
        self._finished = False
        self._escape_timer = QTimer(self)
        self._escape_timer.setInterval(30)
        self._escape_timer.timeout.connect(self._poll_escape)

    # -- 生命周期 -----------------------------------------------------------
    def start(self):
        try:
            self._bounds = native.desktop_bounds()
            with physical_pixel_context(native._u):
                screen = ImageGrab.grab(all_screens=True).convert('RGB')
            expected = (self._bounds[2] - self._bounds[0],
                        self._bounds[3] - self._bounds[1])
            if screen.size != expected:
                raise OSError('屏幕尺寸已变化，请重新取色。')
            self._image = screen
            self._provider.set_image(_pil_to_qimage(screen))
            self._open_window()
        except Exception as exc:      # noqa: BLE001 - 任何异常都回到 UI
            self._finish(error=exc)

    def _open_window(self):
        engine = QQmlApplicationEngine()
        engine.addImageProvider('frozen', self._provider)
        ctx = engine.rootContext()
        ctx.setContextProperty('eyedropper', self)
        ctx.setContextProperty('eyedropperImageSize',
                               [self._image.size[0], self._image.size[1]])
        engine.load(QUrl.fromLocalFile(str(_qml_dir() / 'Eyedropper.qml')))
        roots = engine.rootObjects()
        if not roots:
            raise OSError('取色界面加载失败，请重试。')

        window = roots[0]
        self._engine = engine
        self._window = window

        # 窗口铺满虚拟桌面：逻辑尺寸 = 物理尺寸 / DPR，渲染后正好 1:1 物理像素
        screen = window.screen()
        dpr = screen.devicePixelRatio() if screen is not None else 1.0
        self._dpr = dpr
        left, top, right, bottom = self._bounds
        window.setProperty('pixelWidth', right - left)
        window.setProperty('pixelHeight', bottom - top)
        window.setGeometry(int(round(left / dpr)), int(round(top / dpr)),
                           int(round((right - left) / dpr)),
                           int(round((bottom - top) / dpr)))
        window.show()
        self._verify_and_pin()
        self._escape_timer.start()

    def _verify_and_pin(self):
        """确认窗口客户区与物理桌面完全重合；同时确保不激活、置顶。"""
        user = native._u
        hwnd = user.GetAncestor(int(self._window.winId()), 2)
        if not hwnd:
            raise OSError('无法确认取色窗口，请重试。')

        from overlay_native import configure_overlay, unregister_overlay
        try:
            configure_overlay(int(hwnd), passive=False)
            left, top, right, bottom = self._bounds
            with physical_pixel_context(native._u):
                # SWP_NOACTIVATE | SWP_SHOWWINDOW，位置与尺寸按物理像素给出
                if not user.SetWindowPos(int(hwnd), -1, left, top,
                                         right - left, bottom - top, 0x50):
                    raise OSError('无法显示取色窗口，请重试。')
                rect, origin = W.RECT(), W.POINT()
                if (not user.GetClientRect(int(hwnd), C.byref(rect))
                        or not user.ClientToScreen(int(hwnd), C.byref(origin))):
                    raise OSError('无法读取取色窗口边界，请重试。')
                actual = (origin.x, origin.y,
                          origin.x + rect.right, origin.y + rect.bottom)
                if actual != (left, top, right, bottom):
                    raise OSError('取色窗口与屏幕像素不一致，请重试。')
        except Exception:
            unregister_overlay(int(hwnd))
            raise

    def _poll_escape(self):
        if self._finished:
            return
        if native.escape_pressed():
            self._finish()

    # -- 交互（QML 调用） ---------------------------------------------------
    # 注意：这些方法**必须**加 @Slot 才能被 QML 调用。
    # 纯 Python 方法不会进入 Qt 元对象，QML 里 eyedropper.confirm() 会静默失效
    # ——表现为「点吸管弹出全屏取色层，但单击/右键/Esc 都没反应、取不到色」。
    # 之前 start / _poll_escape 之所以能用，是因为它们被 QTimer 信号连接，
    # PySide 顺带把它们注册成了槽，掩盖了这个问题。
    @Slot(float, float, result=str)
    def preview(self, logical_x, logical_y):
        """返回 (hex, 标签位置是否翻转)，用于悬浮标签。

        坐标换算用**物理光标**而不是 QML 逻辑坐标 —— 后者会被 window DPR
        再缩一次，与"物理像素取色"的语义不符。
        """
        if self._finished or self._image is None:
            return ''
        try:
            x, y = self._physical_point()
            return pixel_hex(self._image, x, y)
        except (ValueError, OSError):
            return ''

    def _physical_point(self):
        cursor_x, cursor_y = native.physical_cursor()
        return frozen_image_point(cursor_x, cursor_y, self._bounds[:2],
                                  self._image.size)

    def _current_hex(self):
        try:
            return pixel_hex(self._image, *self._physical_point())
        except (ValueError, OSError) as exc:
            self._finish(error=exc)
            return None

    @Slot()
    def confirm(self):
        if self._finished:
            return
        color = self._current_hex()
        if color is not None:
            self._finish(color=color)

    @Slot()
    def cancel(self):
        self._finish()

    # -- 收尾 ---------------------------------------------------------------
    def _finish(self, color=None, error=None):
        if self._finished:
            return
        self._finished = True
        self._escape_timer.stop()

        # 取色层必须在**本轮事件循环之后**再销毁。
        # confirm()/cancel() 是从 QML 的 JS 栈里调进来的，如果这里同步把
        # _engine 置空、窗口 close，QQmlApplicationEngine 会在 JS 仍在执行时
        # 被析构 —— 实测直接段错误（应用闪退，看起来就是「点吸管没反应」）。
        # 所以先摘掉窗口的原生注册，再把真正的关闭/释放排到下一轮。
        window = self._window
        engine = self._engine
        hwnd = 0
        if window is not None:
            try:
                user = native._u
                hwnd = user.GetAncestor(int(window.winId()), 2)
            except Exception:
                hwnd = 0
        self._window = None
        self._engine = None

        # 用列表持有 engine：闭包里 del 局部名会变成局部变量而非释放外层引用
        holder = [engine]

        def teardown():
            if hwnd:
                try:
                    from overlay_native import unregister_overlay
                    unregister_overlay(int(hwnd))
                except Exception:
                    pass
            if window is not None:
                try:
                    window.close()
                except RuntimeError:
                    pass
            # 到这里才真正释放 engine
            holder.clear()

        QTimer.singleShot(0, teardown)

        host = self._host
        if host is not None:
            host.picking = False
            setattr(host, '_eyedropper', None)
            updater = getattr(host, 'updater', None)
            if updater is not None:
                try:
                    updater.set_busy(bool(getattr(host, 'busy', False)))
                except Exception:
                    pass

        if error is not None:
            if host is not None:
                host.status.configure(text=tr('屏幕取色失败：') + tr(str(error)))
        elif color is not None and callable(self._callback):
            self._callback(color)


def pick_screen(host, callback):
    """Qt 版入口，签名与原 ``eyedropper.pick_screen(root, callback)`` 一致。"""
    if getattr(host, 'picking', False) or getattr(host, 'busy', False):
        return
    host.picking = True
    session = QtEyedropper(host, callback)
    setattr(host, '_eyedropper', session)
    # 让出一帧，避免在主窗按钮的点击事件里同步创建全屏窗口
    QTimer.singleShot(120, session.start)