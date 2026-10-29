"""软件更新对话框（Qt 版）。

替换原 `updater.ui_update.UpdateUI` 的**承载方式**，不改更新器本身：

* 事件仍然由 `UpdateRuntime` 产生，经 `business.handle_event('update', …)`
  转到本类——`business.py` 一行未改；
* 文案仍然取自 `updater.ui_update.update_copy()` / `text()`，
  五语翻译与「有新版本 x.y.z」等措辞不做二次创作；
* 下载、取消、安装、忽略、导入离线包全部调用 `UpdateRuntime` 的原有方法，
  本类只负责按钮可用性与进度显示。

`UpdateUI.handle(event)` 是原版的调用契约，这里保留同名方法，
所以 `QtHost` 只要把 `self.update_ui` 指向本类，业务侧无需任何适配。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

import i18n
from qt_ui import dialogs as _dialogs

# 动作顺序与原 Tk 版一致（检查 / 下载 / 安装 / 取消 / 忽略 / 离线 / 稍后）
ACTIONS = ('check', 'download', 'install', 'cancel', 'ignore', 'offline', 'later')


def _ui_update():
    """延迟导入：只有真正用到更新对话框时才加载这个模块。"""
    from updater import ui_update
    return ui_update


class UpdatePanel(QObject):
    """更新对话框的状态与动作。QML 只读 ``view``，不自持业务状态。"""

    changed = Signal()

    def __init__(self, host, runtime, parent=None):
        super().__init__(parent)
        self._host = host
        self._runtime = runtime
        self.last = dict(kind='idle')
        self._origin = None          # 下载速度基准 (monotonic, received)
        self._window = None
        self._engine = None
        self._button = ''

    # ------------------------------------------------------------------
    # 与原 UpdateUI 相同的入口
    # ------------------------------------------------------------------
    def handle(self, event):
        """由 `business.handle_event` 调用。事件字典原样传入，不改键名。"""
        import time
        if event['kind'] == 'download':
            now = time.monotonic()
            if self.last.get('kind') != 'download':
                self._origin = (now, event['received'])
            origin = self._origin or (now, event['received'])
            event = dict(event, speed=max(0.0, (event['received'] - origin[1])
                                          / max(0.01, now - origin[0])))
        self.last = event
        if event['kind'] == 'exit_requested':
            # 安装器要求退出：与原版一样先标记，再走正常关闭流程
            # （Qt 侧关闭动作挂在 aboutToQuit → host.shutdown）。
            self._host._update_install_exit = True
            QGuiApplication.quit()
            return
        self.refresh()

    def label(self):
        """顶栏按钮文案：有可用更新时显示「有新版本 x.y.z」。"""
        copy = self._copy()
        service = self._runtime.service
        version = self._version()
        if version and service.state in ('available', 'ready'):
            return copy['title']
        return _ui_update().text('check', i18n.language)

    def refresh(self):
        self._button = self.label()
        if hasattr(self._host, 'state'):
            self._host.state.apply(updateLabel=self._button)
        self.changed.emit()

    # ------------------------------------------------------------------
    # 对话框
    # ------------------------------------------------------------------
    @Slot()
    def open(self):
        if self._window is not None:
            try:
                self._window.raise_()
                self._window.requestActivate()
                return
            except RuntimeError:
                self._window = None
        engine = _dialogs._ensure_engine()
        ctx = engine.rootContext()
        ctx.setContextProperty('updatePanel', self)
        engine.load(QUrl.fromLocalFile(str(_dialogs._qml_dir() / 'UpdateDialog.qml')))
        roots = engine.rootObjects()
        if not roots:
            return
        window = roots[0]
        # 引擎必须被持有，否则 Python 回收后窗口消失
        window._engine = engine
        window.visibleChanged.connect(self._on_visible)
        self._window = window
        self._engine = engine
        from qt_ui import window_fx
        window_fx.present(window, getattr(self._host, 'window', None))
        self.refresh()

    def _on_visible(self):
        if self._window is not None and not self._window.isVisible():
            self._window = None
            self._engine = None

    def _close(self):
        if self._window is not None:
            try:
                self._window.close()
            except RuntimeError:
                pass
        self._window = None
        self._engine = None

    # ------------------------------------------------------------------
    # 动作：全部转发给 UpdateRuntime，不在这里判断能否更新
    # ------------------------------------------------------------------
    @Slot(str)
    def act(self, key):
        if key == 'check':
            self._runtime.check(manual=True)
        elif key == 'download':
            self._runtime.download()
        elif key == 'install':
            self._install()
        elif key == 'cancel':
            self._runtime.cancel()
        elif key == 'ignore':
            self._ignore()
        elif key == 'offline':
            self._pick_offline()
        elif key == 'later':
            self._close()

    def _install(self):
        self._runtime.set_busy(self.operation_busy())
        if self._runtime.service.busy:
            self.handle(dict(kind='blocked', reason='busy'))
            return
        if not self._host.flush_autosave():
            return
        self._runtime.install()

    def _ignore(self):
        manifest = self._runtime.service.manifest
        if manifest is not None:
            self._runtime.preference(ignored=manifest.version)
        self._close()
        self._button = _ui_update().text('check', i18n.language)
        self.refresh()

    def _pick_offline(self):
        """离线包选择交给 QML 的文件对话框，选完把路径原样交给 runtime。"""
        if self._window is not None:
            try:
                self._window.requestOfflinePick()
            except (AttributeError, RuntimeError):
                pass

    @Slot(str)
    def offlinePicked(self, url):
        """QML 传回的是 file:// URL，转成本地路径后交给 runtime。"""
        from PySide6.QtCore import QUrl

        raw = str(url or '')
        path = QUrl(raw).toLocalFile() if raw.startswith('file:') else raw
        if path:
            self._runtime.offline(path)

    @Slot(bool)
    def setAutomatic(self, value):
        self._runtime.preference(automatic=bool(value))
        self.refresh()

    @Slot(bool)
    def setPrerelease(self, value):
        self._runtime.preference(prerelease=bool(value))
        self.refresh()

    def operation_busy(self):
        """与原版同义：进行中的取色/选窗/寻色都算忙。"""
        return (self._host.busy or self._host.picking
                or self._host.__dict__.get('_window_selecting', False)
                or self._host.__dict__.get('_color_selecting', False))

    # ------------------------------------------------------------------
    # 视图数据
    # ------------------------------------------------------------------
    def _version(self):
        event = self.last
        return (event.get('version')
                or getattr(self._runtime.service.manifest, 'version', '') or '')

    def _copy(self):
        event = self.last
        size = event.get('download_bytes',
                         getattr(self._runtime.service.plan, 'download_bytes', 0))
        return _ui_update().update_copy(i18n.language, self._version() or '', size or 0)

    def _body(self):
        text = _ui_update().text
        lang = i18n.language
        event = self.last
        kind = event['kind']
        copy = self._copy()
        if kind == 'available':
            body = copy['detail']
        elif kind == 'idle':
            body = text('checking_notice', lang)
        elif kind in _ui_update().TEXTS:
            body = text(kind, lang)
        elif event.get('reason') == 'bootstrap_required':
            body = text('manual', lang)
        else:
            body = text(event.get('reason') or 'verification', lang)
        if kind == 'download':
            fmt = _ui_update().format_bytes
            body = (f"{fmt(event['received'])} / {fmt(event['total'])}"
                    f" · {fmt(event.get('speed', 0))}/s")
        if event.get('conflicts'):
            body += '\n' + text('conflicts', lang)
        return body

    def _actions(self):
        text = _ui_update().text
        copy = self._copy()
        service = self._runtime.service
        state = service.state
        version = self._version()
        busy = self.operation_busy()
        rows = []
        for key in ACTIONS:
            enabled = (key in ('later', 'offline', 'check')
                       or (key == 'download' and state == 'available')
                       or (key == 'install' and state == 'ready')
                       or (key == 'cancel' and state in ('checking', 'downloading'))
                       or (key == 'ignore' and bool(version)))
            if key in ('offline', 'download', 'install') and busy:
                enabled = False
            rows.append({
                'key': key,
                'label': copy.get(key, text(key, i18n.language)),
                'enabled': bool(enabled),
                'primary': key in ('download', 'install'),
            })
        return rows

    def _progress(self):
        event = self.last
        service = self._runtime.service
        visible = (event['kind'] == 'download'
                   or service.state in ('downloading', 'installing'))
        received = float(event.get('received', 0) or 0)
        total = float(event.get('total', 0) or 0)
        value = min(1.0, received / total) if total > 0 else 0.0
        fmt = _ui_update().format_bytes
        text = (f"{fmt(received)} / {fmt(total)}" if total > 0
                else _ui_update().text('installing', i18n.language))
        return visible, value, text

    def _get_data(self):
        lang = i18n.language
        ui = _ui_update()
        copy = self._copy()
        version = self._version()
        event = self.last
        visible, value, progress_text = self._progress()
        return {
            'title': ui.text('title', lang),
            'heading': copy['title'] if version else ui.text('title', lang),
            'body': self._body(),
            'notice': ui.text('checking_notice', lang),
            'offlineNotice': ui.text('offline_notice', lang),
            'autoLabel': ui.text('automatic', lang),
            'preLabel': ui.text('prerelease', lang),
            'automatic': bool(self._runtime.prefs.get('automatic', True)),
            'prerelease': bool(self._runtime.prefs.get('prerelease', False)),
            'actions': self._actions(),
            'progressVisible': visible,
            'progressValue': value,
            'progressText': progress_text,
            'kind': event['kind'],
            'busy': self.operation_busy(),
            'busyNotice': ui.text('busy', lang) if self.operation_busy() else '',
        }

    # 名字不能叫 data：QObject 自带 data（默认属性），会遮蔽自定义属性
    view = Property('QVariantMap', _get_data, notify=changed)
