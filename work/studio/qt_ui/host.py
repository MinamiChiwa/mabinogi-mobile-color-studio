"""Qt 宿主：继承 `business.Business`，把业务方法的界面调用投影到 QML。

业务方法读写 ``self.q`` / ``self.cards`` / ``self.status`` / ``self.start`` 等
实例属性；``configure(...)`` 由 ``qt_ui.core`` 的适配器接住，转成 `UiState`
字段。本文件只负责界面投影与生命周期（启动、更新确认、关闭），
不放寻色、判色或方案格式相关的逻辑。
"""
from __future__ import annotations

import json
import queue
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QGuiApplication

import business as core
import i18n
import theme as ui_theme
from i18n import tr

from qt_ui import QML_DIR
from qt_ui.core import CardLabelShim, MenuShim, UiState, VarShim, _pil_to_data_uri
from qt_ui.bridge import Bridge


# ---------------------------------------------------------------------------
# 卡片：变量与外观投影；规则字典由 business.RuleSource 生成
# ---------------------------------------------------------------------------
class QtCard(core.RuleSource):
    """区域卡片的变量与显示投影。

    `rule()` 由 business.RuleSource 提供，即送进引擎的规则字典。
    """

    def __init__(self, host, index):
        self.host = host
        self.index = index
        self.session_available = True

        store = {'enabled': True, 'target': '#202020', 'alt': '',
                 'mode': '精准 HEX', 'tolerance': 8.0, 'priority': index + 1}

        def bind(key, cast=None):
            def getter():
                value = store[key]
                return cast(value) if cast is not None else value

            def setter(value):
                store[key] = value
                # 目标色 / 模式 / 容差会改变「允许色集合」，需要重算缩略图；
                # 其它字段只刷新显示。
                if key in ('target', 'mode', 'tolerance'):
                    self.preview()
                else:
                    self.refresh()

            return VarShim(getter, setter)

        self._store = store
        self.enabled = bind('enabled', bool)
        self.target = bind('target')
        self.alt = bind('alt')
        self.mode = bind('mode')
        self.tolerance = bind('tolerance', float)
        self.priority = bind('priority', int)

        # 业务方法会调用 card.priority_menu.set(...)；优先级显示由 refresh() 投影。
        self.priority_menu = MenuShim(lambda _kw: None)
        self.current = CardLabelShim(self._sink_current, self, 'current')
        self.best_label = CardLabelShim(self._sink_best, self, 'best')

        self._palette_pixels = None
        self._palette_key = None
        self._display_key = None
        self._preview_job = None
        self._palette_future = None
        self._last_exact = None

        self.refresh()

    # -- 供业务方法调用 -----------------------------------------------------
    def refresh_language(self):
        self._host_refresh_language()

    def _host_refresh_language(self):
        pass

    def change_mode(self, *_args):
        """模式变化要重算允许色集合；判色规则仍由 rule() 负责。"""
        self.preview()

    def set_session_available(self, available):
        changed = self.session_available != available
        self.session_available = bool(available)
        if changed or not available:
            self.refresh()

    def preview(self, *_args):
        """目标色/模式/容差变化：先排一次 80ms 防抖的色板计算，再刷新显示。"""
        self.schedule_palette()
        self.refresh()

    def _draw_palette(self):
        self._preview_job = None
        self.host.schedule_palette(self)

    def schedule_palette(self):
        """80ms 防抖，连续输入只算最后一次。"""
        job = self._preview_job
        if job is not None:
            try:
                self.host.after_cancel(job)
            except Exception:
                pass
        self._preview_job = self.host.after(80, self._draw_palette)

    def open_palette(self, *_args):
        pass

    def pick(self):
        self.host.pick_color_for(self)

    # -- 显示投影 -----------------------------------------------------------
    def _sink_current(self, kwargs):
        text = kwargs.get('text')
        if text is not None:
            # 形如「当前颜色  #123456」，把色值单独拆出
            value = ''
            for token in str(text).split():
                if token.startswith('#'):
                    value = token
                    break
            self.host.state.card(self.index,
                                 current=getattr(text, 'source', text),
                                 currentHex=value, currentDot=value)
        color = kwargs.get('fg_color')
        if color:
            self.host.state.card(self.index, currentDot=color)

    def _sink_best(self, kwargs):
        """把业务方法的 ``best_label.configure(text='#RRGGBB · ΔE 3.20', fg_color=...)``
        投影成读数区需要的三段：色点、HEX、ΔE 与徽标。

        徽标只读 ``self.rule()`` —— 也就是送进引擎的那份规则字典，
        不复制判色逻辑，因此不会与寻色结果产生分歧。
        """
        changes = {}
        raw = kwargs.get('text')
        if raw is not None:
            changes['best'] = raw
            head, sep, tail = str(raw).partition('·')
            hex_text = head.strip() if sep else str(raw).strip()
            tail = tail.strip() if sep else ''
            # 「实测颜色  —」这类占位文字不是色值
            if hex_text and not hex_text.startswith('#'):
                hex_text = ''
            changes['bestHex'] = hex_text
            changes['bestDelta'] = tail
            changes['bestDot'] = hex_text
            # ΔE 槽位只放色差本身；「未参与匹配」这类说明交给徽标
            changes['deText'] = tail if 'ΔE' in tail else 'ΔE —'
            changes.update(self._badge(hex_text, tail))
        if 'fg_color' in kwargs:
            color = kwargs['fg_color']
            changes['bestBg'] = color
            # fg_color 是实测色，同步成读数区色点
            if str(color).startswith('#') and str(color).upper() != '#28364A':
                changes['bestDot'] = color
        if 'text_color' in kwargs:
            changes['bestText'] = kwargs['text_color']
        if changes:
            self.host.state.card(self.index, **changes)

    def _badge(self, hex_text, tail):
        """达标徽标。判据完全来自 ``rule()``，不另立阈值。"""
        if '未参与' in tail:
            return {'badge': '未参与', 'badgeTone': 'mute'}
        if not hex_text:
            return {'badge': '未开始', 'badgeTone': 'mute'}
        digits = ''.join(ch for ch in tail.split('ΔE')[-1] if ch.isdigit() or ch == '.') \
            if 'ΔE' in tail else ''
        try:
            delta = float(digits) if digits else None
        except ValueError:
            delta = None
        if delta is None:
            return {'badge': '未开始', 'badgeTone': 'mute'}
        rule = self.rule()
        if not rule.get('enabled'):
            return {'badge': '未启用', 'badgeTone': 'mute'}
        ok = delta == 0 if rule.get('exact') else delta <= rule.get('tolerance', 0)
        return ({'badge': '达标', 'badgeTone': 'good'} if ok
                else {'badge': '未达标', 'badgeTone': 'warn'})

    def refresh(self):
        self.host.refresh_card(self)


# ---------------------------------------------------------------------------
# Qt 宿主
# ---------------------------------------------------------------------------
class QtHost(core.Business, QObject):
    def __init__(self):
        super().__init__()
        self.state = UiState()
        self.bridge = Bridge(self, self.state)

        # ---- 业务方法读写的数据属性 ----
        self.selected_window = None
        self._bound_target = None
        self.overlay = None
        self.active_rules = None
        self.active_region_count = 3
        self.best_summary = None
        self.history = core.read_history(core.DATA / 'history.json')
        self.q = queue.Queue()
        self.runner = None
        self.busy = False
        self.picking = False
        self.keys = {}
        self.cards = []
        self._closing = False
        # 更新后首次启动：`--update-ready <事务目录>`，确认提交前不启用热键、不写设置。
        self._update_health_pending = '--update-ready' in sys.argv
        self._update_transaction = (Path(sys.argv[sys.argv.index('--update-ready') + 1])
                                    if self._update_health_pending else None)
        self._loading_profile = False
        self._profile_read_failed = False
        self._autosave_job = None
        self._dialogs = {}
        self._window_selecting = False
        self._color_selecting = False
        self._retry_enabled = False
        self._native_candidate_batch = None
        self._native_candidate_closed = False
        # 主窗口：对话框/浮窗以它为锚点定位（由 app.py 注入）
        self.window = None
        self._last_palette_job = {}

        # ---- 策略与服务器 ----
        self._strategy_defaults = core.migrate_strategy_defaults(
            core.DATA, persist=not self._update_health_pending)
        saved_server = core.read_settings(core.DATA / 'settings.json').get('server', 'tw')
        if '--validate-korean-build' in sys.argv:
            saved_server = 'kr'
        elif '--validate-japanese-build' in sys.argv:
            saved_server = 'jp'
        if saved_server not in dict(core.SERVER_OPTIONS):
            saved_server = 'tw'

        server_store = {'value': saved_server}
        self.server = VarShim(lambda: server_store['value'],
                              lambda v: server_store.__setitem__('value', v))

        selected = self._strategy_defaults['settings'].get('search_strategy', 'screenshot')
        strategy_store = {'value': selected if selected in ('native', 'screenshot') else 'screenshot'}
        self.search_strategy = VarShim(lambda: strategy_store['value'],
                                       lambda v: strategy_store.__setitem__('value', v))

        # ---- 业务方法写入的界面投影 ----
        self.status = _StatusSink(self, 'status')
        self.detail = _TextSink(self, 'detail')
        self.footer = _TextSink(self, 'footer')
        self.strategy_note = _TextSink(self, 'strategyNote')
        self.region_note = _VisibilitySink(self, 'regionNote')
        self.window_button = _TextSink(self, 'windowLabel')
        self.start = _StartSink(self)
        self.strategy_menu = MenuShim(lambda kw: self._apply_menu('strategy', kw),
                                      on_select=self.change_search_strategy)
        self.server_menu = MenuShim(lambda kw: self._apply_menu('server', kw),
                                   on_select=self.change_server)

        # ---- 计时器：after()/after_cancel() 的 QTimer 登记 ----
        self._timers = {}

        for index in range(3):
            card = QtCard(self, index)
            card.host = self
            self.cards.append(card)

        self._hotkeys_stop = threading.Event()
        self._hotkey_thread = threading.Thread(target=self.hotkey_loop, daemon=True)

        # 更新器：go()/pick_window() 依赖 updater.service.state 做安装期保护。
        from updater.runtime import UpdateRuntime
        self.updater = UpdateRuntime(
            core.installation_root(), core.DATA, core.APP_VERSION,
            lambda event: self.q.put(('update', event)))

        # business.handle_event 把 'update' 事件交给 self.update_ui.handle(d)。
        from qt_ui.update import UpdatePanel
        self.update_ui = UpdatePanel(self, self.updater)

        # 对话框各自用独立 QML 引擎，需要显式注入主题状态
        from qt_ui import dialogs as qt_dialogs
        qt_dialogs.bind_state(self.state)

        # 语言/服务器/策略的初始投影
        self.state.apply(language=i18n.language)
        self.refresh_server_label()
        self.refresh_window_label()
        self.refresh_language()

        self.load()

        for card in self.cards:
            for key in ('enabled', 'target', 'alt', 'mode', 'tolerance'):
                getattr(card, key).trace_add('write', self.schedule_autosave)

        if self.history:
            self.display_best(self.history[0])

        for card in self.cards:
            self.schedule_palette(card)

        # 浮窗预创建；失败时留 None，go() 开始寻色时会再调 _make_overlay() 重试。
        try:
            self.overlay = self._make_overlay()
        except Exception:
            self.overlay = None

    @property
    def update_health_pending(self):
        return self._update_health_pending

    def _make_overlay(self):
        """构造寻色浮窗（business.go 在 overlay 为 None 时调用）。"""
        from qt_ui.overlay import QtOverlay
        return QtOverlay(
            self,
            lambda *a, **k: self.stop(source='overlay_stop_button'),
            self.select_candidate,
            settings_path=core.DATA / 'settings.json')

    def attach_window(self, window):
        """主窗口就绪后调用：登记引用，并转给对话框模块做定位锚点。"""
        self.window = window
        from qt_ui import dialogs as qt_dialogs
        qt_dialogs.bind_window(window)

    def show_notice(self, kind, title, message):
        """业务提示（流程中断、完成）：用信息对话框显示纯文本标题与正文。"""
        from qt_ui import dialogs as qt_dialogs
        body = str(message or '')
        # 正文常带换行，InfoDialog 用段落列表承载
        sections = [('', body)] if body else []
        try:
            qt_dialogs.show_info(self.window, str(title or ''), sections)
        except Exception:                                  # noqa: BLE001
            # 对话框构造失败时至少把内容落到状态栏，不要让流程静默中断
            self.state.apply(status=f'{title} · {body}'[:160])

    def after(self, ms, callback=None, *_args):
        timer = QTimer(self)
        timer.setSingleShot(True)
        token = id(timer)
        self._timers[token] = timer

        def fire():
            self._timers.pop(token, None)
            try:
                if callback is not None:
                    callback()
            finally:
                # 关键：QTimer 的 parent 是 host，只从 _timers 移除并不会释放
                # C++ 对象。每次 after() 都会留下一个 QTimer 子对象，长时间运行
                # 会累积到几十万个，导致事件分发越来越慢。用完必须销毁。
                timer.deleteLater()

        timer.timeout.connect(fire)
        timer.start(max(0, int(ms)))
        return token

    def after_idle(self, callback):
        return self.after(0, callback)

    def after_cancel(self, token):
        timer = self._timers.pop(token, None)
        if timer is not None:
            timer.stop()

    def update_idletasks(self):
        pass

    def report_callback_exception(self, exc_type=None, exc=None, tb=None):
        import traceback
        traceback.print_exception(exc_type, exc, tb)

    # ------------------------------------------------------------------
    # 界面投影
    # ------------------------------------------------------------------
    def _apply_menu(self, which, kwargs):
        if 'values' in kwargs:
            if which == 'strategy':
                self.state.apply(strategyValues=list(kwargs['values']))
            elif which == 'server':
                self.state.apply(serverValues=list(kwargs['values']))
        if 'value' in kwargs:
            if which == 'strategy':
                value = kwargs['value']
                short_native = str(tr('精准寻色'))
                # business 在忙时会把长标签（含说明）写回来，这里统一成短名
                if value and value.startswith(short_native):
                    value = short_native
                self.state.apply(strategyValue=value)
            elif which == 'server':
                self.state.apply(serverLabel=kwargs['value'])

    def refresh_card(self, card):
        store = card._store
        exact = store['mode'] == '精准 HEX'
        available = bool(card.session_available)
        enabled = bool(store['enabled']) and available

        try:
            swatch = core.normalize_hex(store['target'])
            light = sum(int(swatch[i:i + 2], 16) for i in (1, 3, 5)) > 430
            swatch_text_color = '#17202B' if light else '#FFFFFF'
        except (ValueError, IndexError):
            swatch = ui_theme.color('placeholder')
            swatch_text_color = ui_theme.color('text')

        alts = []
        for part in store['alt'].replace('，', ',').split(',')[:6]:
            try:
                alts.append(core.normalize_hex(part))
            except ValueError:
                pass

        enable_text = ('已启用' if enabled else '未启用') if available else '本局不可用'

        # HEX 合法性：只做格式判断，取值与校验函数沿用原模块
        try:
            core.normalize_hex(store['target'])
            target_valid = True
        except ValueError:
            target_valid = False

        self.state.card(
            card.index,
            enabled=enabled,
            available=available,
            target=store['target'],
            alt=store['alt'],
            alts=alts,
            exact=exact,
            mode=store['mode'],
            tolerance=float(store['tolerance']),
            priority=int(store['priority']),
            enableText=enable_text,
            enableColor=ui_theme.color('accent') if enabled else ui_theme.color('muted'),
            # 卡片底色按原型 .card：常态 --panel + 1px --line；
            # 「启用」由开关与 .6 透明度表达，不做整卡染色。
            cardBg=ui_theme.color('panel'),
            cardLine=ui_theme.color('line'),
            cardBorder=1,
            swatchColor=swatch,
            swatchTextColor=swatch_text_color,
            swatchText='点击选色' if enabled else ('未启用' if available else '本局不可用'),
            sliderEnabled=not exact,
            targetValid=target_valid,
            hint=('颜色要求：六位 HEX 必须一致' if exact
                  else f"颜色要求：色差 ΔE ≤ {float(store['tolerance']):.0f} · 越小越接近目标"),
        )

    # 业务方法会调用 self.set_detail(text)
    def set_detail(self, text):
        self.state.apply(detail=text or '', detailVisible=bool(text))

    # 业务方法会调用 self.status.configure(...)
    def refresh_language(self):
        """重绘所有文案（业务方法在切换策略、载入方案后调用）。"""
        self.state.apply(
            appSubtitle=f'瑪奇 Mobile  /  by 南千和  ·  v{core.APP_VERSION}',
            appVersion=core.APP_VERSION,
            languages=list(i18n.LANGUAGES),
            language=i18n.language,
            # 文案只放简体中文原文，显示由 QML 的 Loc.t() 翻译；
            # 这样切语言时不需要 Python 重新推一遍，也不会残留旧语言。
            headerActions=[
                {'key': 'support', 'label': '支持作者', 'kind': 'ghost'},
                {'key': 'github', 'label': 'GitHub', 'kind': 'secondary'},
                {'key': 'update', 'label': '检查更新', 'kind': 'secondary'},
                {'key': 'tutorial', 'label': '?', 'kind': 'secondary'},
            ],
            toolbarActions=[
                {'key': 'save', 'label': '保存方案', 'kind': 'secondary'},
                {'key': 'history', 'label': '寻色记录', 'kind': 'secondary'},
            ],
        )
        self.refresh_window_label()
        self.refresh_server_label()
        # 策略下拉用「短名 + 当前语言」：business.change_search_strategy 比较的正是
        # tr('截图寻色') / tr('精准寻色')，沿用同一套字符串才不会在英文界面失效。
        short_native = str(tr('精准寻色'))
        short_shot = str(tr('截图寻色'))
        self.strategy_menu.configure(values=[short_shot, short_native])
        self.strategy_menu.set(short_native if self.search_strategy.get() == 'native'
                               else short_shot)
        native = self.search_strategy.get() == 'native'
        self.state.apply(
            strategyNote=('警示：精准寻色会读取游戏内存，风险较高。' if native
                          else '寻色方式：截图寻色。不读取游戏内存。'),
            strategyWarn=native,
        )
        for card in self.cards:
            card.refresh()

        # 顶栏「检查更新 / 有新版本 x.y.z」也要跟着语言刷新
        panel = getattr(self, 'update_ui', None)
        if panel is not None:
            panel.refresh()

    def refresh_window_label(self):
        target = self.selected_window
        # 自动检测时显示检测到的窗口标题；没有唯一窗口时 title 留空，由 QML 显示翻译后的提示
        if target is not None:
            title = target.title
            text = '游戏窗口 · ' + title
        else:
            try:
                title = core.resolve_target(server=self.server.get()).title
            except RuntimeError:
                title = ''
            text = '自动检测 · ' + (title or '未检测到唯一窗口')
        self.state.apply(
            windowLabel=text if len(text) <= 34 else text[:31] + '…',
            windowTitle=title,
            windowBound=target is not None)

    def refresh_server_label(self):
        # 值保持原文；UiCombo 显示时翻译，回调拿到的仍是原文
        self.server_menu.configure(values=[label for _, label in core.SERVER_OPTIONS])
        self.server_menu.set(dict(core.SERVER_OPTIONS)[self.server.get()])

    # ------------------------------------------------------------------
    # 业务方法会用到的辅助入口
    # ------------------------------------------------------------------
    def pick_color(self, callback):
        """屏幕吸管：安装更新期间禁用；取色本体在 qt_ui.eyedropper。"""
        updater = getattr(self, 'updater', None)
        if updater is not None and updater.service.state in ('installing', 'waiting_for_exit'):
            return
        if updater is not None:
            updater.set_busy(True)
        from qt_ui.eyedropper import pick_screen as qt_pick_screen
        qt_pick_screen(self, callback)

    def _push_picker(self, card, state):
        self.state.card(
            card.index,
            pickerOpen=True,
            pickerGrid=state.grid,
            pickerHue=state.hue,
            pickerSat=state.sat,
            pickerLig=state.lig,
            pickerNeutral=state.neutral,
            pickerRecent=state.recent,
            pickerCommon=state.common,
            pickerTitle=state.title,
            pickerSatTrack=state.satTrack,
            pickerLigTrack=state.ligTrack,
        )

    def open_picker(self, card):
        """打开某张卡片的色板（不做 toggle；由 QML 决定开关时机）。"""
        if getattr(self, 'busy', False):
            return False
        current = getattr(self, '_inline_picker_index', None)
        if current is not None and current != card.index:
            self.state.card(current, pickerOpen=False, pickerGrid=[])
        self._inline_picker_index = card.index

        from qt_ui import picker as picker_mod
        state = picker_mod.PickerState()
        try:
            state.set_context(
                card.target.get(),
                tolerance=float(card.tolerance.get()),
                exact=card.mode.get() == '精准 HEX',
                available=bool(card.session_available),
                recent=getattr(card, '_recent_colors', []))
        except ValueError:
            state.set_context('#000000', available=bool(card.session_available))

        card._picker_state = state
        self._push_picker(card, state)
        state.changed.connect(lambda: self._push_picker(card, state))
        return True

    def open_atlas(self, card):
        """生成目标色集合预览（浮层用），像素仍来自原色板计算链路。"""
        current = getattr(self, '_atlas_index', None)
        if current is not None and current != card.index:
            self.state.card(current, atlasOpen=False)
        self._atlas_index = card.index
        pixels = getattr(card, '_palette_pixels', None)
        if pixels is None or not len(pixels):
            self.state.card(card.index, atlasOpen=True, atlasImage='',
                            atlasNote='暂无可用颜色', atlasWidth=0, atlasHeight=0)
            return
        from palette import full_atlas
        image = full_atlas(pixels)
        count = len(pixels)
        if card.mode.get() == '精准 HEX':
            note = f'精准 HEX · {count:,} 色'
        else:
            note = f'ΔE ≤ {float(card.tolerance.get()):.0f} · {count:,} 色'
        self.state.card(
            card.index,
            atlasOpen=True,
            atlasImage=_pil_to_data_uri(image),
            atlasNote=note,
            atlasCount=count,
            atlasWidth=image.width,
            atlasHeight=image.height,
        )

    def close_atlas(self):
        idx = getattr(self, '_atlas_index', None)
        if idx is not None:
            self.state.card(idx, atlasOpen=False)
            self._atlas_index = None

    def close_inline_picker(self):
        idx = getattr(self, '_inline_picker_index', None)
        if idx is not None:
            self.state.card(idx, pickerOpen=False, pickerGrid=[])
            self._inline_picker_index = None

    def apply_inline_picker(self, card, h, sat, lig):
        """HSL 拖动/点格后写回目标色。"""
        state = getattr(card, '_picker_state', None)
        if state is None:
            return
        if h is not None and sat is not None and lig is not None:
            state.adjust(int(h), int(sat), int(lig))
        card.target.set(state.target)

    def pick_inline_cell(self, card, row, col):
        state = getattr(card, '_picker_state', None)
        if state is None:
            return
        state.pick_cell(row, col)
        card.target.set(state.target)

    def pick_inline_color(self, card, value):
        state = getattr(card, '_picker_state', None)
        if state is None:
            return
        state.pick_color(value)
        card.target.set(state.target)

    def open_color_picker(self, card):
        """自绘目标色浮窗（设计稿 7.4）。选色结果写回同一组 tk 变量替身。"""
        if getattr(self, 'busy', False):
            return
        from qt_ui import picker as picker_mod
        from PySide6.QtCore import QUrl
        from PySide6.QtQml import QQmlApplicationEngine

        state = picker_mod.PickerState()
        try:
            state.set_context(
                card.target.get(),
                tolerance=float(card.tolerance.get()),
                exact=card.mode.get() == '精准 HEX',
                available=bool(card.session_available),
                recent=getattr(card, '_recent_colors', []))
        except ValueError:
            state.set_context('#000000', available=bool(card.session_available))

        engine = QQmlApplicationEngine()
        ctx = engine.rootContext()
        ctx.setContextProperty('uiState', self.state)
        ctx.setContextProperty('bridge', self.bridge)
        ctx.setContextProperty('pickerState', state)
        ctx.setContextProperty('pickerCardIndex', card.index)
        engine.load(QUrl.fromLocalFile(str(QML_DIR / 'ColorPicker.qml')))
        roots = engine.rootObjects()
        if not roots:
            return
        window = roots[0]
        window._engine = engine
        window.setProperty('cardIndex', card.index)

        start = card.target.get()
        recent = list(getattr(card, '_recent_colors', []))

        def on_visible_changed():
            if window.isVisible():
                return
            current = state.target
            if current != start:
                card.target.set(current)
                recent.insert(0, start)
                card._recent_colors = recent[:6]
            self._picker_window = None

        window.visibleChanged.connect(on_visible_changed)
        self._picker_window = window
        from qt_ui import window_fx
        # 锚定到目标色块：靠近色块的右侧/下方弹，并夹在屏幕可用区内
        anchor = self.window
        window_fx.present(window, anchor)

    def pick_color_for(self, card):
        """点目标色块（QtCard.pick）：打开自绘目标色浮窗。"""
        self.open_color_picker(card)

    def open_github(self):
        import webbrowser
        webbrowser.open(core.GITHUB)

    # ---- 对话框登记 ---------------------------------------------------
    #
    # QML 的 Window.close() 只是隐藏，对象仍然存活。原实现只在 `_dialogs`
    # 里判「非 None」，于是关掉教程后按钮就再也打不开了。这里改为按
    # 「是否可见」判断，并在窗口隐藏时清空登记。
    def _dialog_open(self, key):
        window = self._dialogs.get(key)
        if window is None:
            return False
        try:
            visible = window.isVisible()
        except RuntimeError:          # C++ 对象已销毁
            self._dialogs[key] = None
            return False
        if not visible:
            self._dialogs[key] = None
            return False
        try:
            window.raise_()
            window.requestActivate()
        except (AttributeError, RuntimeError):
            pass
        return True

    def _track_dialog(self, key, window):
        self._dialogs[key] = window
        if window is None:
            return
        try:
            window.visibleChanged.connect(lambda: self._forget_dialog(key, window))
        except (AttributeError, RuntimeError):
            pass

    def _forget_dialog(self, key, window):
        if self._dialogs.get(key) is window:
            try:
                if not window.isVisible():
                    self._dialogs[key] = None
            except RuntimeError:
                self._dialogs[key] = None

    # ---- 对话框：内容仍由原模块提供，这里只换承载方式 ----------------
    def show_support(self):
        from qt_ui import dialogs
        AFDIAN, PATREON, GITHUB = core.AFDIAN, core.PATREON, core.GITHUB
        if self._dialog_open('support'):
            return
        window = dialogs.show_info(
            None, tr('支持作者'),
            [(tr('赞助完全自愿'), tr('赞助完全自愿，不论是否赞助，都可以正常使用本工具的全部功能。')),
             (tr('说明'), tr('选择您偏好的平台支持后续开发，感谢您的支持。'))],
            [(tr('爱发电'), AFDIAN), ('Patreon', PATREON), ('GitHub', GITHUB)])
        self._track_dialog('support', window)

    def show_tutorial(self):
        from qt_ui import dialogs
        TUTORIAL, GITHUB = core.TUTORIAL, core.GITHUB
        if self._dialog_open('tutorial'):
            return
        window = dialogs.show_info(
            None, tr('使用教程'),
            [(tr(h), tr(b)) for h, b in TUTORIAL],
            [(tr('提交问题 / Issues'), GITHUB + '/issues')])
        self._track_dialog('tutorial', window)

    def show_history(self):
        """寻色记录：读取 self.history（已由 result_history 生成）。"""
        from qt_ui import dialogs
        if self._dialog_open('history'):
            return
        rows = []
        for row in self.history:
            rows.append({
                'time': row.get('time', ''),
                'outcome': row.get('outcome', ''),
                'maximum': row.get('maximum'),
                'average': row.get('average'),
                'regions': [{
                    'region': r.get('region', 0),
                    'color': r.get('color') or '',
                    'delta': r.get('delta'),
                } for r in row.get('regions', [])],
            })
        window = dialogs.show_history(None, rows)
        self._track_dialog('history', window)

    def save(self):
        """染色方案：预设存储与校验仍由 profile_store 负责。"""
        from qt_ui import dialogs
        from profile_store import PresetStore
        if self._dialog_open('presets'):
            return
        window = dialogs.show_presets(
            None, PresetStore(core.DATA / 'presets.json'),
            self.current_profile, self.apply_profile)
        self._track_dialog('presets', window)

    def pick_window(self):
        """选择游戏窗口：列表与可用性判断仍由 window_target 负责。"""
        from qt_ui import dialogs
        updater = getattr(self, 'updater', None)
        if updater is not None and updater.service.state in ('installing', 'waiting_for_exit'):
            return
        if self.busy:
            self.status.configure(text='请先按 F9 停止，再更换游戏窗口。')
            return
        if self._dialog_open('window'):
            return
        server = self.server.get()

        def selected(target):
            # 窗口在弹窗期间被切换过服务器就放弃，避免张冠李戴
            if server != self.server.get():
                return
            self.apply_window_target(target)

        window = dialogs.show_window_picker(None, server, self.selected_window, selected)
        self._track_dialog('window', window)

    def apply_window_target(self, target):
        """采用一个新的游戏窗口（浮层与旧弹窗共用这一条路径）。"""
        if self.busy:
            self.status.configure(text='请先按 F9 停止，再更换游戏窗口。')
            return False
        self.selected_window = target
        self.refresh_window_label()
        self.status.configure(text='窗口选择已更新，下次开始时生效。')
        self._dialogs['window'] = None
        return True

    def show_update_dialog(self):
        """软件更新对话框；状态由 UpdateRuntime 事件驱动。"""
        if getattr(self, 'updater', None) is None:
            return
        self.update_ui.open()

    def after_language_changed(self):
        self.refresh_language()

    def schedule_palette(self, card):
        """色板预览：后台计算允许色集合，只把结果显示到 QML。"""
        key = card._palette_key
        try:
            target = core.normalize_hex(card.target.get())
        except ValueError:
            self.state.card(card.index, paletteNote='请输入有效 HEX', paletteImage='')
            return
        exact = card.mode.get() == '精准 HEX'
        wanted = (target, 0 if exact else float(card.tolerance.get()))
        if wanted == key:
            return
        card._palette_key = wanted
        if card._palette_future is not None:
            card._palette_future.cancel()

        if exact:
            card._palette_pixels = core.np.array([core.rgb(target)], core.np.uint8)
            self._render_palette(card)
            return

        future = core.PALETTE_POOL.submit(core.build_preview, *wanted)
        card._palette_future = future

        def poll():
            if wanted != card._palette_key or future is not card._palette_future:
                return
            if not future.done():
                self.after(100, poll)
                return
            try:
                card._palette_pixels, image = future.result()
            except Exception:
                self.state.card(card.index, paletteNote='预览计算失败，请重新选择颜色')
                return
            self._render_palette(card, image)

        self.after(100, poll)

    def _render_palette(self, card, image=None):
        if image is None:
            image = core.overview(card._palette_pixels)
        card._display_key = card._palette_key
        count = len(card._palette_pixels)
        # 说明文字按原型 .atlas__note 的形式：<条件> · <色数> 色
        if card._palette_key and not card._palette_key[1]:
            note = f'精准 HEX · {count:,} 色'
        else:
            note = f'ΔE ≤ {float(card.tolerance.get()):.0f} · {count:,} 色'
        self.state.card(
            card.index,
            paletteImage=_pil_to_data_uri(image),
            paletteNote=note,
            paletteCount=count,
        )

    # ------------------------------------------------------------------
    def start_services(self):
        # tick 用 after(60) 自续，只启动一次；再叠一个周期定时器会让 tick 链成倍增长。
        self.after(60, self.tick)
        if self._update_health_pending:
            self._begin_update_confirmation()
            return
        self._hotkey_thread.start()
        # 仅打包运行时静默检查；结果只改顶栏按钮文案，不弹窗。
        if getattr(sys, 'frozen', False):
            self.after(3000, self.updater.check)

    # ------------------------------------------------------------------
    # 更新后首次启动：通知更新助手「界面已就绪」，等它提交后再开放操作
    # ------------------------------------------------------------------
    def _begin_update_confirmation(self):
        from update_bootstrap import signal_ready
        self.start.configure(state='disabled')
        self.after_idle(lambda: signal_ready(self._update_transaction))
        self.after(100, self._await_update_commit)

    def _await_update_commit(self):
        try:
            state = json.loads((self._update_transaction / 'state.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            state = {}
        if state.get('status') == 'committed':
            core.migrate_strategy_defaults(core.DATA)
            self._update_health_pending = False
            self._hotkey_thread.start()
            if self.window is not None:
                self.window.show()
            self.start.configure(state='normal')
            self.after(3000, self.updater.check)
            return
        from update_bootstrap import helper_alive
        if not helper_alive(self._update_transaction):
            # 助手已退出却没有提交：更新被回滚，本进程不应继续运行。
            self.close()
            return
        self.after(100, self._await_update_commit)

    # ------------------------------------------------------------------
    # 关闭：标题栏按钮、任务栏关闭、Alt+F4 和安装更新都走这里
    # ------------------------------------------------------------------
    def close(self):
        if self._closing:
            return
        self._closing = True
        self.updater.cancel()
        if self.busy:
            # 先停寻色并释放鼠标，等工作线程结束后再退出。
            self.stop(source='window_close')
            self._closing = False
            QTimer.singleShot(250, self.close)
            return
        self.shutdown()
        QGuiApplication.quit()

    def shutdown(self):
        """释放计时器与热键并保存设置；可重复调用（aboutToQuit 也会触发）。"""
        self._closing = True
        for timer in list(self._timers.values()):
            timer.stop()
        self._timers.clear()
        self._hotkeys_stop.set()
        if not self._profile_read_failed or self._autosave_job is not None:
            self.flush_autosave()


# ---------------------------------------------------------------------------
# 轻量 sink：把 configure(text=) 投影到 UiState
# ---------------------------------------------------------------------------
class _TextSink:
    def __init__(self, host, field):
        self._host = host
        self._field = field
        self._state = {}
        self._visible = True

    def configure(self, **kwargs):
        self._state.update(kwargs)
        if 'text' in kwargs:
            # business 传进来的可能已经是 tr() 的 DisplayText；
            # 取回原文存进状态，显示时再由 QML 按当前语言翻译。
            text = kwargs['text']
            self._host.state.apply(**{self._field: getattr(text, 'source', text)})

    def cget(self, key):
        return self._state.get(key, '')

    def grid(self, **_kwargs):
        self._visible = True

    def grid_remove(self):
        self._visible = False

    def grid_forget(self):
        self._visible = False

    def pack(self, **_kwargs):
        self._visible = True

    def winfo_exists(self):
        return True

    def winfo_children(self):
        return []

    def destroy(self):
        pass


class _VisibilitySink(_TextSink):
    def configure(self, **kwargs):
        super().configure(**kwargs)
        if 'text' in kwargs:
            text = kwargs['text']
            source = getattr(text, 'source', text)
            self._host.state.apply(regionNote=source,
                                   regionNoteVisible=bool(source))

    def grid_remove(self):
        self._host.state.apply(regionNoteVisible=False)

    def grid(self, **_kwargs):
        self._host.state.apply(regionNoteVisible=True)


class _StatusSink(_TextSink):
    """状态主行：额外推断状态点颜色（只按文案前缀判断，不改业务）。"""

    def configure(self, **kwargs):
        super().configure(**kwargs)
        text = self._state.get('text', '')
        tone = 'idle'
        if '正在' in text or '寻色' in text or '已就绪' in text:
            tone = 'live'
        if '停止' in text or '警告' in text or '剩余时间' in text:
            tone = 'warn'
        if '失败' in text or '错误' in text or '无法' in text:
            tone = 'error'
        self._host.state.apply(statusTone=tone)


class _StartSink:
    """开始按钮：只需提供一个 enabled 投影。"""

    def __init__(self, host):
        self._host = host
        self._enabled = True

    def configure(self, **kwargs):
        state = kwargs.get('state')
        if state is not None:
            self._enabled = state != 'disabled'
            self._host.state.apply(startEnabled=self._enabled)

    def cget(self, key):
        return 'normal' if self._enabled else 'disabled'

    def grid(self, **_kwargs):
        pass