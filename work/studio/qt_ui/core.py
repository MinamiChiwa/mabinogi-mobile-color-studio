"""Qt Quick 界面层：展示状态与控件适配器。

设计约束：

* 本包**只做展示**。寻色、判色、方案读写、事件处理都在 `business.Business`，
  不在这里重新实现、也不改写任何返回值。
* 适配器让业务方法里形如 ``self.status.configure(text=...)`` 的调用落到 QML 上。
* 颜色与圆角一律取自 `theme`，不新增字面量。
"""
from __future__ import annotations

import base64
import io

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

import theme as ui_theme


# ---------------------------------------------------------------------------
# 变量适配器：业务方法通过 .get() / .set() 读写卡片与设置
# ---------------------------------------------------------------------------
class VarShim:
    """提供 ``.get()`` / ``.set()`` / ``.trace_add()``。

    QtHost 给卡片变量挂 ``trace_add('write', schedule_autosave)`` 实现自动保存。
    """

    __slots__ = ('_get', '_set', '_traces')

    def __init__(self, getter, setter):
        self._get = getter
        self._set = setter
        self._traces = []

    def get(self):
        return self._get()

    def set(self, value):
        self._set(value)
        for callback in tuple(self._traces):
            callback(None, None, 'write')

    def trace_add(self, _mode, callback):
        self._traces.append(callback)

    # tk 变量在业务代码里偶尔会被当作值直接使用，这里不做隐式转换，
    # 强制调用方写 .get()，避免出现"偶发字符串化"的隐性差异。


# ---------------------------------------------------------------------------
# 控件适配器：把 configure(...) / cget(...) 转成状态写入
# ---------------------------------------------------------------------------
class _Shim:
    """通用基类：把 Tk 的 configure/cget 转发给一个接收函数。"""

    __slots__ = ('_sink', '_state')

    def __init__(self, sink):
        self._sink = sink          # (kwargs) -> None
        self._state = {}

    def configure(self, **kwargs):
        self._state.update(kwargs)
        self._sink(kwargs)

    # Tk 允许位置参数形式 configure('text', value)，业务代码里未使用，
    # 这里显式拒绝，避免静默忽略。
    def cget(self, key):
        return self._state.get(key, '')

    def grid(self, **_kwargs):
        self._state['_visible'] = True

    def grid_remove(self):
        self._state['_visible'] = False

    def grid_forget(self):
        self._state['_visible'] = False

    def pack(self, **_kwargs):
        self._state['_visible'] = True

    def pack_forget(self):
        self._state['_visible'] = False

    def pack_propagate(self, *_args):
        pass

    def bind(self, *_args, **_kwargs):
        pass

    def winfo_children(self):
        return []

    def winfo_exists(self):
        return True

    def winfo_toplevel(self):
        return self


class MenuShim(_Shim):
    """CTkOptionMenu / CTkSegmentedButton 的替身。

    ``values`` 与 ``set`` 都要支持，因为 ``refresh_language`` 会同时用两者。
    额外暴露 ``current`` 供 QML 读取当前显示值。
    """

    __slots__ = ('_on_select',)

    def __init__(self, sink, on_select=None):
        super().__init__(sink)
        self._on_select = on_select

    def set(self, value):
        self.configure(value=value)

    # QML 下拉选中时调用
    def choose(self, value):
        if self._on_select is not None:
            self._on_select(value)


class CardLabelShim(_Shim):
    """卡片内某个文字/色块标签的替身。

    ``display_colors`` / ``clear_run_readings`` / ``set_session_available``
    都会对 ``card.best_label`` 和 ``card.current`` 调 ``configure(text=…,
    fg_color=…, text_color=…)``。这里把三者映射到卡片的显示字段，
    取值全部沿用原调用方传入的值，不在这里做任何判定。
    """

    __slots__ = ('_card', '_kind')

    def __init__(self, sink, card, kind):
        super().__init__(sink)
        self._card = card
        self._kind = kind

    def configure(self, **kwargs):
        self._state.update(kwargs)
        self._sink(kwargs)


# ---------------------------------------------------------------------------
# 展示状态：QML 的唯一数据源
# ---------------------------------------------------------------------------
def _pil_to_data_uri(image):
    """把 PIL 图像转成 QML 可直接使用的 data URI。

    用 data URI 而不是 QQuickImageProvider，是为了避免异步加载导致
    色板闪一下空白；色板尺寸固定（240x48）且很小，内联开销可忽略。
    圆角由 QML 的 ``RoundedImage``（Canvas）负责，图片本身保持方形铺满。
    """
    if image is None:
        return ''
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode('ascii')


def _card_defaults(index):
    return {
        'index': index,
        'title': f'区域 {index + 1}',
        'enabled': True,
        'available': True,
        'target': '#202020',
        'alt': '',
        'alts': [],
        'mode': '精准 HEX',
        'exact': True,
        'tolerance': 8.0,
        'priority': index + 1,
        'enableText': '已启用',
        'enableColor': ui_theme.color('accent'),
        'cardBg': ui_theme.color('card_on'),
        'cardLine': ui_theme.color('card_on_line'),
        'cardBorder': 2,
        'swatchText': '点击选色',
        'swatchColor': ui_theme.color('placeholder'),
        'swatchTextColor': ui_theme.color('text'),
        'paletteNote': '',
        'paletteCount': 0,
        'paletteImage': '',
        # 目标色集合浮层：完整色图（按需生成，不常驻）
        'atlasOpen': False,
        'atlasImage': '',
        'atlasNote': '',
        'atlasCount': 0,
        'atlasWidth': 0,
        'atlasHeight': 0,
        'hint': '',
        'sliderEnabled': False,
        'current': '当前颜色  —',
        'best': '实测颜色  —',
        'bestBg': '#28364A',
        'bestText': ui_theme.color('muted'),
        'targetValid': True,
        'bestHex': '',
        'bestDelta': '',
        'currentHex': '',
        # 读数区呈现（原型 .reads）：色点 / ΔE 文本 / 徽标
        'currentDot': '',
        'bestDot': '',
        'deText': 'ΔE —',
        'badge': '未开始',
        'badgeTone': 'mute',
        # 就地色板（第 2 项）：状态挂在卡片上，QML 在卡内渲染
        'pickerOpen': False,
        'pickerGrid': [],
        'pickerHue': 0,
        'pickerSat': 0,
        'pickerLig': 0,
        'pickerNeutral': False,
        'pickerRecent': [],
        'pickerCommon': [],
        'pickerTitle': '',
        'pickerSatTrack': ['#000000', '#FFFFFF'],
        'pickerLigTrack': ['#000000', '#808080', '#FFFFFF'],
    }


class UiState(QObject):
    """所有 QML 绑定的数据来源。任何写入都只影响显示。"""

    changed = Signal()
    cardsChanged = Signal()
    languageChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        # changed 会触发全部 QML 绑定重算，单次约 1.2ms（实测）。
        # 寻色高峰期一次 tick 内会有上百次写入，逐次 emit 会把主线程吃掉；
        # 这里合并成「一轮事件循环发一次」。
        self._emit_pending = False
        self._cards = [_card_defaults(i) for i in range(3)]
        self._status = '就绪 · 请先选择游戏窗口和目标颜色'
        self._detail = ''
        self._detailVisible = False
        self._footer = 'F9 随时停止并释放鼠标  ·  切换窗口停止寻色  ·  不自动开启下一瓶染色剂'
        self._windowLabel = '游戏窗口 · 自动检测'
        self._windowTitle = ''
        self._serverLabel = '台服'
        self._serverValues = []
        self._strategyValues = []
        self._strategyValue = '截图寻色'
        self._strategyNote = '寻色方式：截图寻色。不读取游戏内存。'
        self._strategyWarn = False
        self._regionNote = ''
        self._regionNoteVisible = False
        self._startEnabled = True
        self._running = False
        self._language = '简体中文'
        self._languages = []
        self._headerActions = []
        self._toolbarActions = []
        self._appSubtitle = ''
        self._appVersion = ''
        self._revision = 0
        self._statusTone = 'idle'
        self._logLines = []
        self._logExpanded = False
        self._windowBound = False
        self._appearance = ui_theme.theme.appearance
        self._updateLabel = '检查更新'
        # 最近一次浮层定位（供自检与调试读取；不影响任何交互）
        self._popover = {}

    # -- 标量 ---------------------------------------------------------------
    def _get_status(self):
        return self._status

    status = Property(str, _get_status, notify=changed)

    def _get_detail(self):
        return self._detail

    detail = Property(str, _get_detail, notify=changed)

    def _get_detailVisible(self):
        return self._detailVisible

    detailVisible = Property(bool, _get_detailVisible, notify=changed)

    def _get_footer(self):
        return self._footer

    footer = Property(str, _get_footer, notify=changed)

    def _get_windowTitle(self):
        return self._windowTitle

    windowTitle = Property(str, _get_windowTitle, notify=changed)

    def _get_windowLabel(self):
        return self._windowLabel

    windowLabel = Property(str, _get_windowLabel, notify=changed)

    def _get_serverLabel(self):
        return self._serverLabel

    serverLabel = Property(str, _get_serverLabel, notify=changed)

    def _get_strategyValues(self):
        return self._strategyValues

    strategyValues = Property('QVariantList', _get_strategyValues, notify=changed)

    def _get_strategyValue(self):
        return self._strategyValue

    strategyValue = Property(str, _get_strategyValue, notify=changed)

    def _get_strategyNote(self):
        return self._strategyNote

    strategyNote = Property(str, _get_strategyNote, notify=changed)

    def _get_strategyWarn(self):
        return self._strategyWarn

    strategyWarn = Property(bool, _get_strategyWarn, notify=changed)

    def _get_regionNote(self):
        return self._regionNote

    regionNote = Property(str, _get_regionNote, notify=changed)

    def _get_regionNoteVisible(self):
        return self._regionNoteVisible

    regionNoteVisible = Property(bool, _get_regionNoteVisible, notify=changed)

    def _get_startEnabled(self):
        return self._startEnabled

    startEnabled = Property(bool, _get_startEnabled, notify=changed)

    def _get_running(self):
        return self._running

    running = Property(bool, _get_running, notify=changed)

    def _get_language(self):
        return self._language

    # 语言单独发信号：所有 `Loc.t(...)` 绑定只依赖这一条，
    # 运行期的状态刷新（寻色进度等）不会连带重算全部文案。
    language = Property(str, _get_language, notify=languageChanged)

    def _get_languages(self):
        return self._languages

    languages = Property('QVariantList', _get_languages, notify=changed)

    def _get_serverValues(self):
        return self._serverValues

    serverValues = Property('QVariantList', _get_serverValues, notify=changed)

    def _get_headerActions(self):
        return self._headerActions

    headerActions = Property('QVariantList', _get_headerActions, notify=changed)

    def _get_toolbarActions(self):
        return self._toolbarActions

    toolbarActions = Property('QVariantList', _get_toolbarActions, notify=changed)

    def _get_appSubtitle(self):
        return self._appSubtitle

    appSubtitle = Property(str, _get_appSubtitle, notify=changed)

    def _get_appVersion(self):
        return self._appVersion

    appVersion = Property(str, _get_appVersion, notify=changed)

    # 状态点色：idle / live / warn / error
    def _get_statusTone(self):
        return self._statusTone

    statusTone = Property(str, _get_statusTone, notify=changed)

    # 运行日志：最近若干条
    def _get_logLines(self):
        return self._logLines

    logLines = Property('QVariantList', _get_logLines, notify=changed)

    def _get_logExpanded(self):
        return self._logExpanded

    logExpanded = Property(bool, _get_logExpanded, notify=changed)

    def _get_windowBound(self):
        return self._windowBound

    windowBound = Property(bool, _get_windowBound, notify=changed)

    # 顶栏「检查更新」按钮的文案：有可用更新时变成「有新版本 x.y.z」
    def _get_updateLabel(self):
        return self._updateLabel

    updateLabel = Property(str, _get_updateLabel, notify=changed)

    def _get_popover(self):
        return self._popover

    popover = Property('QVariantMap', _get_popover, notify=changed)

    @Slot(int, str, bool, str, int, int, int, int)
    def reportPopover(self, card, kind, is_open, placement, x, y, w, h):
        """QML 把浮层的实际位置回报给宿主，便于自动化验证与排障。"""
        info = {} if not is_open else {
            'card': card, 'kind': kind, 'placement': placement,
            'x': x, 'y': y, 'width': w, 'height': h,
        }
        if info != self._popover:
            self._popover = info
            self._emit_changed()

    def _get_appearance(self):
        return self._appearance

    appearance = Property(str, _get_appearance, notify=changed)

    def _get_pickerOpenAny(self):
        return any(row.get('pickerOpen') for row in self._cards)

    pickerOpenAny = Property(bool, _get_pickerOpenAny, notify=cardsChanged)

    def set_appearance(self, value):
        if self._appearance != value:
            self._appearance = value
            self._emit_changed()

    def set_logs(self, lines):
        self._logLines = list(lines)
        self._emit_changed()

    def toggle_log(self):
        self._logExpanded = not self._logExpanded
        self._emit_changed()

    def _get_revision(self):
        return self._revision

    revision = Property(int, _get_revision, notify=cardsChanged)

    def _get_cards(self):
        return self._cards

    cards = Property('QVariantList', _get_cards, notify=cardsChanged)

    # -- 写入（仅由适配器调用） ---------------------------------------------
    def _emit_changed(self):
        """合并 changed：同一轮事件循环内只发一次。"""
        if self._emit_pending:
            return
        self._emit_pending = True
        QTimer.singleShot(0, self._flush_changed)

    def _flush_changed(self):
        self._emit_pending = False
        self.changed.emit()

    def apply(self, **changes):
        dirty = False
        for key, value in changes.items():
            attr = '_' + key
            if getattr(self, attr, object()) != value:
                setattr(self, attr, value)
                dirty = True
        if dirty:
            if 'language' in changes:
                self.languageChanged.emit()
            self._emit_changed()

    def card(self, index, **changes):
        if not 0 <= index < len(self._cards):
            return
        row = self._cards[index]
        dirty = False
        for key, value in changes.items():
            if row.get(key) != value:
                row[key] = value
                dirty = True
        if dirty:
            # 替换列表本身，保证 QML 的 QVariantList 绑定收到变更通知。
            self._cards = list(self._cards)
            self._revision += 1
            self.cardsChanged.emit()

    @Slot(int, result='QVariantMap')
    def cardAt(self, index):
        if 0 <= index < len(self._cards):
            return dict(self._cards[index])
        return {}

    @Slot(str, result=str)
    @Slot(str, str, result=str)
    def themeColor(self, name, _appearance=None):
        """取色。第二个参数仅用于让 QML 建立 appearance 依赖：

        QML 只对**属性访问**建立绑定依赖，`themeColor('bg')` 这种函数调用
        不会因为 appearance 变化而重新求值。调用处传 `uiState.appearance`
        作为第二参数，即可让该绑定在主题切换时重算。
        """
        try:
            return ui_theme.color(name)
        except KeyError:
            return '#000000'

    @Slot(str, result=int)
    @Slot(str, str, result=int)
    def themeRadius(self, name, _appearance=None):
        return ui_theme.radius(name)

    @Slot(str, result=float)
    def fontSize(self, name):
        return float(ui_theme.font(name)[0])

    @Slot(str, result=int)
    def fontWeight(self, name):
        return int(ui_theme.font(name)[1])

    @Slot(str, result=int)
    def motion(self, name):
        return ui_theme.motion(name)

    @Slot(str, result=str)
    def tr(self, source):
        """QML 侧的翻译入口（`Loc.t` 最终调到这里）。"""
        if not source:
            return source
        from qt_ui.i18n_qt import translate
        return translate(str(source))