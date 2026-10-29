"""Qt 侧对话框：方案、历史、教程/支持、窗口选择、色板查看器。

原则与主界面一致：**只搬运与展示**。

* 方案对话框读写的是 ``host.current_profile()`` 的返回值，
  校验与规范化仍调用 ``profile_store.canonical_profile``；
* 历史对话框读取 ``host.history``（已由 ``result_history`` 生成）；
* 窗口选择调用 ``window_target.list_windows`` / ``choose_auto`` /
  ``matching_game_windows``，不自己判断窗口是否可用。
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication, QImage, QPixmap
from PySide6.QtQuick import QQuickWindow, QSGRendererInterface
from PySide6.QtQml import QQmlApplicationEngine

import theme as ui_theme
from i18n import tr

_QML_DIR = None
_STATE = None
# 主窗口：对话框以它为锚点居中，避免系统把窗口丢到屏幕角落
_PARENT = None

# 已创建的对话框引擎与窗口：验证脚本据此统计告警、统一关闭。
# 只是登记簿，不改变任何交互行为。
_OPEN: list = []
QML_WARNINGS: list[str] = []


def _register(engine, window):
    def collect(ws):
        QML_WARNINGS.extend(str(w.toString()) for w in ws)

    engine.warnings.connect(collect)
    _OPEN.append((engine, window))


def close_all():
    """关闭本模块创建的全部对话框（验证脚本用完即收）。"""
    while _OPEN:
        engine, window = _OPEN.pop()
        try:
            window.close()
        except RuntimeError:
            pass
        try:
            engine.deleteLater()
        except RuntimeError:
            pass



def bind_window(window):
    """由 QtHost 注入主窗口，作为对话框的定位参照。"""
    global _PARENT
    _PARENT = window


def bind_state(state):
    """由 `QtHost` 注入 `UiState`。

    对话框各自用独立引擎，**不会**继承主窗口的 context property。
    少了这一句，QML 里的 ``uiState.themeColor(...)`` 全是 undefined，
    对话框会退回 Qt 默认白底黑字——功能正常但完全脱离 V7 配色。
    """
    global _STATE
    _STATE = state


def _qml_dir():
    global _QML_DIR
    if _QML_DIR is None:
        from pathlib import Path
        _QML_DIR = Path(__file__).resolve().parent / 'qml'
    return _QML_DIR


def _ensure_engine():
    """每个对话框一个独立引擎，避免共享 context 造成互相覆盖。"""
    engine = QQmlApplicationEngine()
    if _STATE is not None:
        engine.rootContext().setContextProperty('uiState', _STATE)
    return engine


def _show(qml_name, setup=None):
    engine = _ensure_engine()
    ctx = engine.rootContext()
    if setup is not None:
        setup(ctx)
    engine.load(QUrl.fromLocalFile(str(_qml_dir() / qml_name)))
    roots = engine.rootObjects()
    if not roots:
        return None, None
    _register(engine, roots[0])
    return engine, roots[0]


# ---------------------------------------------------------------------------
# 色板查看器
# ---------------------------------------------------------------------------
def _pil_to_qimage(image):
    """PIL -> QImage，保留原始像素，不做平滑。"""
    if image.mode != 'RGB':
        image = image.convert('RGB')
    data = image.tobytes('raw', 'RGB')
    qimage = QImage(data, image.width, image.height, image.width * 3,
                    QImage.Format.Format_RGB888)
    # QImage 不持有 data 的所有权，必须 copy
    return qimage.copy()


def open_palette_viewer(host, colors, target, *, pool=None):
    """展示完整允许色图。像素与目标色来自调用方，本函数不重新计算。"""
    from palette import full_atlas
    # 原先这里还有 `import palette_viewer as legacy`，但从未使用；
    # 而它 import tkinter + customtkinter，会让 Qt 入口把 Tk 整套拉起来。
    # 查看器本身是 Viewer.qml，不依赖它。

    future = None
    if pool is not None:
        future = pool.submit(full_atlas, colors)
    else:
        image = full_atlas(colors)

    class _Ctl(QObject):
        ready = Signal(str, int, int)

        @Slot()
        def fit(self):
            pass

    engine = _ensure_engine()
    ctx = engine.rootContext()
    ctx.setContextProperty('viewerTarget', target)
    ctx.setContextProperty('viewerCount', len(colors))
    engine.load(QUrl.fromLocalFile(str(_qml_dir() / 'Viewer.qml')))
    roots = engine.rootObjects()
    if not roots:
        return None
    window = roots[0]
    _register(engine, window)
    from qt_ui import window_fx
    window_fx.present(window, _PARENT)

    def apply_image(img):
        qimg = _pil_to_qimage(img)
        window.setProperty('sourceImage', qimg)

    if future is not None:
        from PySide6.QtCore import QTimer

        def poll():
            if not future.done():
                QTimer.singleShot(100, poll)
                return
            try:
                apply_image(future.result())
            except Exception:
                pass

        QTimer.singleShot(100, poll)
    else:
        apply_image(image)

    # 引擎必须被持有，否则 Python 侧回收导致窗口消失
    window._engine = engine
    return window


# ---------------------------------------------------------------------------
# 简单信息对话框（教程 / 支持）
# ---------------------------------------------------------------------------
def show_info(parent, title, sections, links=()):
    engine = _ensure_engine()
    ctx = engine.rootContext()
    ctx.setContextProperty('dialogTitle', title)
    ctx.setContextProperty('dialogSections', [{'h': h, 'b': b} for h, b in sections])
    ctx.setContextProperty('dialogLinks', [{'label': lab, 'url': url} for lab, url in links])
    engine.load(QUrl.fromLocalFile(str(_qml_dir() / 'InfoDialog.qml')))
    roots = engine.rootObjects()
    if roots:
        roots[0]._engine = engine
        _register(engine, roots[0])
        from qt_ui import window_fx
        window_fx.present(roots[0], _PARENT)
    return roots[0] if roots else None

# ---------------------------------------------------------------------------
# 寻色记录
# ---------------------------------------------------------------------------
def show_history(parent, rows):
    engine = _ensure_engine()
    ctx = engine.rootContext()
    ctx.setContextProperty('historyRows', rows)
    engine.load(QUrl.fromLocalFile(str(_qml_dir() / 'HistoryDialog.qml')))
    roots = engine.rootObjects()
    if roots:
        roots[0]._engine = engine
        _register(engine, roots[0])
        from qt_ui import window_fx
        window_fx.present(roots[0], _PARENT)
    return roots[0] if roots else None


# ---------------------------------------------------------------------------
# 方案对话框
# ---------------------------------------------------------------------------
class PresetBridge(QObject):
    """把 PresetDialog 的按钮动作转给 ``PresetStore`` / host。

    校验、规范化、去重全部由 `profile_store` 完成；
    本类只负责把异常原文回显到界面。
    """

    changed = Signal()
    message = Signal(str, bool)

    def __init__(self, store, collect, apply_profile, parent=None):
        super().__init__(parent)
        self._store = store
        self._collect = collect
        self._apply = apply_profile
        self._rows = []
        self._selected = None
        self.reload()

    def reload(self):
        try:
            self._rows = self._store.rows()
        except ValueError as exc:
            self._rows = []
            self.message.emit(str(exc), True)
        self.changed.emit()

    @Slot(result='QVariantList')
    def presetNames(self):
        return [{'id': r['id'], 'name': r['name']} for r in self._rows]

    @Slot(str, result='QVariantMap')
    def presetProfile(self, preset_id):
        for row in self._rows:
            if row['id'] == preset_id:
                return dict(row['profile'])
        return {}

    @Slot(str, str, result=bool)
    def save(self, name, preset_id):
        """按当前设置保存（保留旧入口，供工具栏「保存方案」直接调用）。"""
        return self.saveProfile(name, preset_id, {})

    @Slot(str, str, 'QVariantMap', result=bool)
    def saveProfile(self, name, preset_id, profile):
        """保存对话框里编辑中的方案。

        profile 为空时退回「当前设置」；否则交给 profile_store 做规范化与校验，
        本类不做任何字段判断。
        """
        payload = dict(profile) if profile else self._collect()
        try:
            self._store.save(name, payload, preset_id=preset_id or None)
        except (ValueError, OSError) as exc:
            self.message.emit(str(exc), True)
            return False
        self.reload()
        self.message.emit('方案已保存。', False)
        return True

    @Slot(str, result=bool)
    def load(self, preset_id):
        try:
            row = self._store.get(preset_id)
        except ValueError as exc:
            self.message.emit(str(exc), True)
            return False
        try:
            self._apply(row['profile'])
        except (ValueError, OSError) as exc:
            self.message.emit(str(exc), True)
            return False
        self.message.emit('方案已载入，当前设置已自动保存。', False)
        return True

    @Slot(str, result=bool)
    def remove(self, preset_id):
        try:
            self._store.delete(preset_id)
        except (ValueError, OSError) as exc:
            self.message.emit(str(exc), True)
            return False
        self.reload()
        self.message.emit('方案已删除。', False)
        return True

    @Slot(result='QVariantMap')
    def current(self):
        return dict(self._collect())


def show_presets(parent, store, collect, apply_profile):
    engine = _ensure_engine()
    ctx = engine.rootContext()
    bridge = PresetBridge(store, collect, apply_profile)
    ctx.setContextProperty('presetBridge', bridge)
    engine.load(QUrl.fromLocalFile(str(_qml_dir() / 'PresetDialog.qml')))
    roots = engine.rootObjects()
    if roots:
        roots[0]._engine = engine
        roots[0]._bridge = bridge
        _register(engine, roots[0])
        from qt_ui import window_fx
        window_fx.present(roots[0], _PARENT)
    return roots[0] if roots else None


# ---------------------------------------------------------------------------
# 窗口选择
# ---------------------------------------------------------------------------
class WindowBridge(QObject):
    """窗口列表来自 `window_target`，本类不判断窗口是否可用。"""

    changed = Signal()
    message = Signal(str)

    def __init__(self, server, current, parent=None):
        super().__init__(parent)
        self._server = server
        self._current = current
        self._choices = []
        self._notice = ''
        self._selected = None
        self.refresh()

    @Slot()
    def refresh(self):
        from window_target import (WindowUnavailable, choose_auto,
                                   list_windows, matching_game_windows)
        from i18n import tr as _tr
        self._choices = []
        auto = str(_tr('自动检测'))
        try:
            windows = list_windows()
            if self._server is not None:
                windows = matching_game_windows(windows, self._server)
            try:
                chosen = choose_auto(windows, server=self._server)
                notice = str(_tr('自动检测到：')) + chosen.title
                auto += ' · ' + chosen.title
            except WindowUnavailable as exc:
                notice = str(_tr(str(exc)))
                auto += ' · ' + str(_tr('未检测到唯一窗口'))
            self._choices.append({'id': '', 'label': auto, 'detail': ''})
            for w in sorted(windows, key=lambda x: x.title.casefold()):
                label = f'{w.title[:48]}'
                detail = f'{w.executable or "PID"} · {w.pid} / {w.hwnd:X}'
                self._choices.append({'id': str(w.hwnd), 'label': label, 'detail': detail})
            self._notice = (notice + '\n'
                            + str(_tr('确认后仅对所选窗口识别；窗口关闭后需重新选择。')))
        except RuntimeError as exc:
            self._notice = str(_tr(str(exc)))
            self._choices = [{'id': '', 'label': auto, 'detail': ''}]
        self.changed.emit()

    @Slot(result='QVariantList')
    def windows(self):
        return self._choices

    @Slot(result=str)
    def notice(self):
        return self._notice


def show_window_picker(parent, server, current, selected):
    engine = _ensure_engine()
    ctx = engine.rootContext()
    bridge = WindowBridge(server, current)
    ctx.setContextProperty('windowBridge', bridge)
    engine.load(QUrl.fromLocalFile(str(_qml_dir() / 'WindowDialog.qml')))
    roots = engine.rootObjects()
    if roots:
        roots[0]._engine = engine
        roots[0]._bridge = bridge

        def pick(hwnd):
            from window_target import list_windows, valid_target
            from i18n import tr as _tr
            if not hwnd:
                selected(None)
                roots[0].close()
                return
            try:
                match = [w for w in list_windows() if str(w.hwnd) == hwnd]
            except RuntimeError:
                match = []
            if not match or not valid_target(match[0]):
                bridge.message.emit(str(_tr('所选窗口已关闭，请重新选择游戏窗口。')))
                return
            selected(match[0])
            roots[0].close()

        roots[0]._pick = pick
        _register(engine, roots[0])
        from qt_ui import window_fx
        window_fx.present(roots[0], _PARENT)
    return roots[0] if roots else None
