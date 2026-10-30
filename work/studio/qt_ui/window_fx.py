"""对话框 / 浮窗的统一出场。

两件事：

1. **定位**：居中到父窗口（没有父窗口则居中屏幕），并夹在屏幕可用区内。
   系统默认摆放会把窗口贴到屏幕边缘，用户还得先挪一下才能用。
2. **滑动出现**：按窗口最终落在屏幕的上半 / 下半选择方向——在上半就从上往下滑，
   在下半就从下往上滑，配合淡入。方向和位置都由屏幕几何决定，不是固定动画。

只做表现，不改变任何窗口的业务行为。
"""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QTimer, QVariantAnimation
from PySide6.QtGui import QGuiApplication

DURATION = 210
OFFSET = 28
MARGIN = 24

# 动画对象必须被持有，否则 Python 侧回收会让动画中途停住
_ANIMS: dict[int, object] = {}


def _area(window, parent=None):
    screen = None
    if parent is not None:
        try:
            screen = parent.screen()
        except RuntimeError:
            screen = None
    if screen is None:
        try:
            screen = window.screen()
        except RuntimeError:
            screen = None
    if screen is None:
        screen = QGuiApplication.primaryScreen()
    return screen.availableGeometry() if screen is not None else None


def place(window, parent=None, *, margin: int = MARGIN) -> tuple[int, int]:
    """算出窗口应有的左上角坐标（已夹进屏幕可用区）。"""
    w, h = window.width(), window.height()
    area = _area(window, parent)
    if parent is not None and parent.isVisible():
        x = parent.x() + (parent.width() - w) // 2
        y = parent.y() + (parent.height() - h) // 2
    elif area is not None:
        x = area.x() + (area.width() - w) // 2
        y = area.y() + (area.height() - h) // 2
    else:
        x = y = 0
    if area is not None:
        # 窗口比可用区更大时不再保留边距，避免被推成负坐标
        mx = min(margin, max(0, (area.width() - w) // 2))
        my = min(margin, max(0, (area.height() - h) // 2))
        x = max(area.x() + mx, min(x, area.x() + area.width() - w - mx))
        y = max(area.y() + my, min(y, area.y() + area.height() - h - my))
    return int(x), int(y)


def direction_for(y: int, height: int, window=None, parent=None) -> str:
    """窗口在上半屏 → 从上往下滑；在下半屏 → 从下往上滑。"""
    area = _area(window, parent) if window is not None else None
    if area is None:
        return 'down'
    return 'down' if (y + height / 2) <= (area.y() + area.height() / 2) else 'up'


def slide_in(window, x: int | None = None, y: int | None = None, *,
             direction: str | None = None, duration: int = DURATION,
             offset: int = OFFSET, show: bool = True,
             final_opacity: float = 1.0) -> None:
    """把窗口放到 (x, y)，并从屏幕对应方向滑入。

    ``final_opacity`` 是淡入的终点：寻色浮窗允许用户设置 65%–100% 的
    不透明度，淡入必须落在该值上，否则动画收尾会把它重置成 1.0。
    """
    try:
        if x is None or y is None:
            x, y = place(window)
        if direction is None:
            direction = direction_for(y, window.height(), window)
        start_y = y - offset if direction == 'down' else y + offset

        window.setPosition(QPoint(int(x), int(start_y)))
        window.setOpacity(0.0)
        if show and not window.isVisible():
            window.show()

        move = QVariantAnimation(window)
        move.setStartValue(float(start_y))
        move.setEndValue(float(y))
        move.setDuration(duration)
        move.setEasingCurve(QEasingCurve.Type.OutCubic)
        move.valueChanged.connect(
            lambda value: window.setPosition(int(x), int(round(float(value)))))

        fade = QPropertyAnimation(window, b'opacity', window)
        fade.setStartValue(0.0)
        fade.setEndValue(float(final_opacity))
        fade.setDuration(duration)
        fade.setEasingCurve(QEasingCurve.Type.OutCubic)

        _ANIMS[id(window)] = (move, fade)
        move.start()
        fade.start()

        # 动画结束后释放引用（窗口关闭时也不会留下悬挂对象）
        def cleanup():
            _ANIMS.pop(id(window), None)

        QTimer.singleShot(duration + 120, window, cleanup)
    except RuntimeError:
        # 窗口已被销毁：忽略
        pass


def stop_fade(window) -> None:
    """用户调整透明度时停止淡入，保留位置动画。"""
    animations = _ANIMS.get(id(window))
    if animations:
        animations[1].stop()


def present(window, parent=None) -> None:
    """按父窗口居中 + 滑动出现。"""
    x, y = place(window, parent)
    slide_in(window, x, y, show=True)
