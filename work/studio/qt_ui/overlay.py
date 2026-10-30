"""Qt 版寻色浮窗。

对外接口（``begin`` / ``render`` / ``handle`` / ``dismiss`` /
``mark_retry_requested``）由 `business.Business` 的寻色流程调用。

窗口原生属性由 `overlay_native` 注册：
``SetWindowDisplayAffinity(hwnd, 0x11)``（截图排除）、
``WS_EX_NOACTIVATE``（不抢焦点）、``WS_EX_TOPMOST``（置顶）。

按需求**不做整窗透明度**；圆角通过透明窗口 + 圆角矩形实现。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal, Slot
from PySide6.QtQml import QQmlApplicationEngine

import overlay_native
from display_geometry import clamp_position, work_area
from i18n import tr
# 阶段名与进度文案都来自原作者模块，不另建一份映射表。
from ui_progress import STAGES, progress_text
from ui_settings import read_settings, save_settings

_QML = Path(__file__).resolve().parent / 'qml'


def _stage_label(stage):
    """阶段 key → 显示名。直接复用 ui_progress.STAGES，缺项时留空。"""
    if not stage:
        return ''
    return STAGES.get(stage, '')


class OverlayState(QObject):
    """浮窗的显示状态。所有文字都由调用方传入，本类不改写。"""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._title = '等待染色界面'
        self._body = ''
        self._elapsed = ''
        self._collapsed = False
        self._retryEnabled = False
        self._running = False
        self._candidates = []
        self._remaining = ''
        self._lowTime = False
        self._progress = -1.0
        self._stopped = False
        self._warn = False
        # 设计稿 overlay-v1.html 的「阶段行」：左侧阶段名 + 右侧步骤/数量
        self._stage = ''
        self._stageMeta = ''
        self._emit_pending = False

    def _emit(self):
        """合并 changed：同一轮事件循环内只发一次。

        浮窗状态在寻色高峰期一轮 tick 里会被写十几次，逐次 emit 会触发
        全部 QML 绑定重算（单次约 1ms 量级），是卡顿来源之一。
        """
        if getattr(self, '_emit_pending', False):
            return
        self._emit_pending = True
        QTimer.singleShot(0, self._flush)

    def _flush(self):
        self._emit_pending = False
        self.changed.emit()

    # title
    def _get_title(self):
        return self._title

    def set_title(self, value):
        if self._title != value:
            self._title = value
            self._emit()

    # body
    def _get_body(self):
        return self._body

    def set_body(self, value):
        if self._body != value:
            self._body = value
            self._emit()

    # elapsed
    def _get_elapsed(self):
        return self._elapsed

    def set_elapsed(self, value):
        if self._elapsed != value:
            self._elapsed = value
            self._emit()

    def _get_collapsed(self):
        return self._collapsed

    def set_collapsed(self, value):
        if self._collapsed != value:
            self._collapsed = value
            self._emit()

    def _get_retryEnabled(self):
        return self._retryEnabled

    def set_retryEnabled(self, value):
        if self._retryEnabled != value:
            self._retryEnabled = value
            self._emit()

    def _get_running(self):
        return self._running

    def set_running(self, value):
        if self._running != value:
            self._running = value
            self._emit()

    def _get_candidates(self):
        return self._candidates

    def set_candidates(self, rows):
        if self._candidates != rows:
            self._candidates = rows
            self._emit()

    from PySide6.QtCore import Property

    def _get_remaining(self):
        return self._remaining

    def set_remaining(self, value, low=False):
        if self._remaining != value or self._lowTime != low:
            self._remaining = value
            self._lowTime = low
            self._emit()

    def _get_lowTime(self):
        return self._lowTime

    def _get_progress(self):
        return self._progress

    def set_progress(self, value):
        if self._progress != value:
            self._progress = value
            self._emit()

    def _get_stopped(self):
        return self._stopped

    def set_stopped(self, value):
        if self._stopped != value:
            self._stopped = value
            self._emit()

    def _get_warn(self):
        return self._warn

    def set_warn(self, value):
        if self._warn != value:
            self._warn = value
            self._emit()

    def _get_stage(self):
        return self._stage

    def set_stage(self, value):
        if self._stage != value:
            self._stage = value
            self._emit()

    def _get_stageMeta(self):
        return self._stageMeta

    def set_stageMeta(self, value):
        if self._stageMeta != value:
            self._stageMeta = value
            self._emit()

    stage = Property(str, _get_stage, notify=changed)
    stageMeta = Property(str, _get_stageMeta, notify=changed)
    remaining = Property(str, _get_remaining, notify=changed)
    lowTime = Property(bool, _get_lowTime, notify=changed)
    progress = Property(float, _get_progress, notify=changed)
    stopped = Property(bool, _get_stopped, notify=changed)
    warn = Property(bool, _get_warn, notify=changed)
    title = Property(str, lambda s: s._title, notify=changed)
    body = Property(str, lambda s: s._body, notify=changed)
    elapsed = Property(str, lambda s: s._elapsed, notify=changed)
    collapsed = Property(bool, lambda s: s._collapsed, notify=changed)
    retryEnabled = Property(bool, lambda s: s._retryEnabled, notify=changed)
    running = Property(bool, lambda s: s._running, notify=changed)
    candidates = Property('QVariantList', lambda s: s._candidates, notify=changed)


class QtOverlay(QObject):
    """寻色浮窗：把寻色事件投影到 QML，Win32 注册交给 `overlay_native`。"""

    def __init__(self, host, stop, select_candidate=None, settings_path=None):
        super().__init__()
        self.host = host
        self.stop_action = stop
        self.select_candidate = select_candidate
        self.settings_path = settings_path
        self.state = OverlayState()
        self.phase = 'waiting'
        self.rules = []
        self.batch_id = None
        self.candidate_rows = {}
        self.default_candidate_id = None
        self._dismissed = True
        self._retry_enabled = False
        self._retry_pending = False
        self._text = None
        self._candidate_data = None
        self._window = None
        self._engine = None
        self.native = None
        # 位置与不透明度：对齐 search_overlay.py:101/240 的读取方式
        self._preferences = read_settings(settings_path) if settings_path else {}
        self._position = self._load_position()
        self._alpha = self._load_alpha()
        self._alpha_timer = None
        # 计时（对齐 search_overlay.py:99 的同名字段）
        self._started = 0.0
        self._stage_started = 0.0
        self._stage = None
        self._deadline = None
        self._heartbeat_timer = None

    # -- 设置存取（对齐 search_overlay.py:181-185）----------------------------
    def _load_position(self):
        value = self._preferences.get('overlay_position', [20, 100])
        try:
            return [int(value[0]), int(value[1])]
        except (TypeError, ValueError, IndexError):
            return [20, 100]

    def _load_alpha(self):
        try:
            return max(0.65, min(1.0, float(self._preferences.get('overlay_alpha', 0.92))))
        except (TypeError, ValueError):
            return 0.92

    def save_position(self):
        """拖动结束后保存位置。"""
        if not self.settings_path or self._window is None:
            return
        self._position = [self._window.x(), self._window.y()]
        try:
            save_settings(self.settings_path, overlay_position=list(self._position))
        except OSError:
            pass

    def set_opacity(self, value):
        """设置浮窗不透明度；250ms 防抖写盘。"""
        try:
            value = max(0.65, min(1.0, float(value)))
        except (TypeError, ValueError):
            return
        self._alpha = value
        if self._window is not None:
            self._window.setOpacity(value)
        if not self.settings_path:
            return
        if self._alpha_timer is not None:
            self._alpha_timer.stop()
        self._alpha_timer = QTimer(self)
        self._alpha_timer.setSingleShot(True)
        self._alpha_timer.timeout.connect(
            lambda: save_settings(self.settings_path, overlay_alpha=float(self._alpha)))
        self._alpha_timer.start(250)

    # -- 窗口 ---------------------------------------------------------------
    def _ensure_window(self):
        if self._window is not None:
            return self._window
        engine = QQmlApplicationEngine()
        ctx = engine.rootContext()
        ctx.setContextProperty('uiState', self.host.state)
        ctx.setContextProperty('overlayState', self.state)
        ctx.setContextProperty('overlayBridge', self)

        from PySide6.QtCore import QUrl as _QUrl
        engine.load(_QUrl.fromLocalFile(str(_QML / 'Overlay.qml')))
        roots = engine.rootObjects()
        if not roots:
            raise RuntimeError('浮窗 QML 加载失败')
        window = roots[0]
        self._engine = engine
        self._window = window

        # 不透明度在窗口真正显示后再应用（见 _apply_alpha）：
        # QWindow 尚未 shown 时设置会被平台的 native handler 忽略。

        # 无边框、置顶、不抢焦点、截图排除
        self._prepare_native()
        return window

    def _apply_alpha(self):
        """把 _alpha 应用到当前窗口。

        必须在 native window 建立之后设置：`show()` 与 `setOpacity()` 在同一
        轮事件循环里时，Windows 平台会忽略这次设置（实测显示后仍为 1.0）。
        因此先排一个 0ms 定时器，等这一帧的处理完成再设。
        """
        if self._window is None:
            return

        def commit():
            if self._window is None:
                return
            try:
                self._window.setOpacity(self._alpha)
            except Exception:                          # noqa: BLE001
                pass

        QTimer.singleShot(0, commit)

    def _prepare_native(self):
        """注册 HWND：截图排除 + 不抢焦点 + 置顶。全部走原模块。"""
        if self._window is None:
            return
        import ctypes as C
        from ctypes import wintypes as W
        user = C.windll.user32
        user.GetAncestor.argtypes = [W.HWND, W.UINT]
        user.GetAncestor.restype = W.HWND
        hwnd = user.GetAncestor(int(self._window.winId()), 2)
        if not hwnd:
            return
        # configure_overlay 返回的是记录 dict（含 hwnd / capture_excluded）
        if self.native is not None:
            overlay_native.unregister_overlay(self.native['hwnd'])
            self.native = None
        self.native = overlay_native.configure_overlay(int(hwnd), passive=True)

    # -- 与 App 约定的接口 --------------------------------------------------
    def begin(self, rules, *, passive=False):
        import time as _time

        self.rules = rules
        self._dismissed = False
        self.phase = 'waiting'
        self._retry_enabled = False
        self._retry_pending = False
        self.state.set_retryEnabled(False)
        self.state.set_running(True)
        self.state.set_stopped(False)
        self.state.set_candidates([])

        # 计时起点：对齐 search_overlay.py:239
        self._started = _time.monotonic()
        self._stage_started = self._started
        self._stage = None
        self._deadline = None

        # 初始文案：对齐 search_overlay.py:252 的 render(...)。
        # 之前缺这一步，浮窗正文一直是空的（只有标题 + 停止按钮）。
        self._text = None
        self.render('等待染色界面',
                    '可从任意游戏界面进入普通染色并完成教学。\n'
                    '识别成功后自动寻色；F9 取消等待。')
        self.update_activity({'stage': 'waiting'})

        window = self._ensure_window()
        self._place(window)
        # 与对话框同一套出场：按窗口所在半屏决定从下往上/从上往下滑
        from qt_ui import window_fx
        window_fx.slide_in(window, window.x(), window.y(), show=True,
                           final_opacity=self._alpha)
        self._prepare_native()

        # 启动每秒计时：对齐 search_overlay.py:254-255
        self._stop_heartbeat()
        self.heartbeat()

    def _stop_heartbeat(self):
        if self._heartbeat_timer is not None:
            self._heartbeat_timer.stop()

    def render(self, title, body):
        value = (title, body)
        if value == self._text:
            return
        self._text = value
        self.state.set_title(tr(title))
        self.state.set_body(tr(body))

    def update_activity(self, data):
        """进度事件：阶段、进度、剩余时间。

        对齐 ``search_overlay.py:207-214`` 的 update_activity：阶段变化要重置
        本阶段计时；带 remaining 时记录截止时刻，由 heartbeat 换算成倒计时。
        额外的字段（current/total）用于驱动 QML 的确定进度条。
        """
        if not isinstance(data, dict):
            return
        import time as _time

        stage = data.get('stage')
        if stage:
            if stage != self._stage:
                self._stage = stage
                self._stage_started = _time.monotonic()
            self.phase = 'waiting' if stage == 'waiting' else 'computing'
            self.state.set_stage(_stage_label(stage))

        if 'remaining' in data and data['remaining'] is not None:
            self._deadline = _time.monotonic() + float(data['remaining'])
            # 立刻反映到界面，避免出现「已给出剩余时间但还显示 --:--」的空档
            left = max(0, int(round(float(data['remaining']))))
            self.state.set_remaining(f'{left // 60:02d}:{left % 60:02d}', low=left <= 10)

        total = data.get('total')
        if total:
            try:
                self.state.set_progress(max(0.0, min(1.0, float(data.get('current', 0)) / float(total))))
            except (TypeError, ValueError, ZeroDivisionError):
                self.state.set_progress(-1.0)
        else:
            self.state.set_progress(-1.0)

        # 阶段内步骤：设计稿右侧的「步骤 3 / 8」
        if total:
            self.state.set_stageMeta(f'{int(data.get("current", 0))} / {int(total)}')

    def heartbeat(self):
        """每秒刷新「已用 / 本阶段」与倒计时（移植 search_overlay.py:215-225）。"""
        import time as _time

        if getattr(self, '_dismissed', True):
            return
        now = _time.monotonic()
        text = f'已用 {int(now - self._started)} 秒 · 本阶段 {int(now - self._stage_started)} 秒'
        if self._deadline is not None:
            text += f' · 游戏剩余 {max(0, int(self._deadline - now))} 秒'
        self.state.set_elapsed(text)

        if self._deadline is not None:
            left = max(0, int(self._deadline - now))
            self.state.set_remaining(f'{left // 60:02d}:{left % 60:02d}', low=left <= 10)
        else:
            # 设计稿等待态显示占位符 --:--
            self.state.set_remaining('--:--')

        if self._heartbeat_timer is None:
            # 只建一次并复用：每秒新建 QTimer 会持续累积子对象
            self._heartbeat_timer = QTimer(self)
            self._heartbeat_timer.setSingleShot(True)
            self._heartbeat_timer.timeout.connect(self.heartbeat)
        self._heartbeat_timer.start(1000)

    def mark_retry_requested(self):
        self._retry_enabled = False
        self._retry_pending = True
        self.state.set_retryEnabled(False)
        self.render('正在重试', '等待当前动作结束后，缩小画板并重新搜索。')

    def dismiss(self):
        self._dismissed = True
        self.phase = 'stopped'
        self._retry_enabled = False
        self.state.set_retryEnabled(False)
        self.state.set_running(False)
        self.state.set_stopped(True)
        self._stop_heartbeat()
        if self.native is not None:
            overlay_native.unregister_overlay(self.native['hwnd'])
            self.native = None
        if self._window is not None:
            self._window.hide()

    def _candidate_rows(self, data):
        """把引擎的候选数据投影成 QML 卡片。

        字段来源与 ``search_overlay.show_candidates`` 一致：
        ``candidates[i]`` 给出颜色/色差，``observations[id]`` 给出实测值，
        ``default_id`` 标记当前方案。这里只做展示映射，不参与任何判定。
        """
        observations = data.get('observations') or {}
        default_id = data.get('default_id')
        strategy = data.get('strategy')
        rows = []
        for item in data.get('candidates', []):
            cid = item.get('id', '')
            # 与 show_candidates 相同：native 或当前方案才带实测观察
            result = observations.get(cid) if (strategy == 'native' or cid == default_id) else None
            measured = bool(result and result.get('verified') and result.get('actual_colors'))
            colors = list(result['actual_colors']) if measured else list(item.get('colors') or [])
            deltas = list(result.get('actual_deltas') or [None] * 3) if measured else \
                     list(item.get('deltas') or [None] * 3)

            is_current = (cid == default_id)
            if measured:
                title = '当前方案 · 游戏实测' if is_current else '已测试方案 · 游戏实测'
            else:
                title = '候选方案 · 预测颜色'

            details = []
            for i, color in enumerate(colors):
                delta = deltas[i] if i < len(deltas) else None
                details.append({
                    'name': f'区域 {i + 1}',
                    'hex': color or '',
                    'delta': '' if delta is None else f'ΔE {delta:.2f}',
                    'empty': not color,
                })

            summary = ''
            source = result if measured else item
            maximum = source.get('maximum')
            average = source.get('average')
            if maximum is not None and average is not None:
                summary = f'最大 {maximum:.2f} / 平均 {average:.2f}'
                exact_total = int(source.get('exact_total') or 0)
                if exact_total:
                    summary = (f"精准命中 {int(source.get('exact_matches') or 0)}/{exact_total} · "
                               + summary)
                accepted = source.get('accepted')
                if accepted is None:
                    summary += ''
                elif accepted:
                    summary += ' · ' + ('实测达标' if measured else '预测达标')
                else:
                    summary += ' · 妥协方案'
                if source.get('family_consistent') is False:
                    summary += ' · 存在色系偏离'

            available = item.get('available', True)
            rows.append({
                'id': cid,
                'title': title,
                'current': is_current,
                'details': details,
                'summary': summary,
                'picked': is_current,
                'action': ('当前方案（实测）' if measured else '当前方案') if is_current
                          else ('选择此方案' if available else '不可用'),
                'disabled': is_current or not available,
            })
        return rows

    def handle(self, kind, data):
        """只处理浮窗要显示的事件；状态与结果判定由 ``Business.handle_event`` 负责。"""
        if getattr(self, '_dismissed', False):
            return
        if not isinstance(data, dict):
            data = {}

        # 进度事件：对齐 search_overlay.py:544-546
        #   phase 切换 + 刷新进度/阶段/剩余 + 用原作者的 progress_text 写标题与正文
        if kind in ('atlas_progress', 'single_progress',
                    'native_progress', 'screenshot_progress'):
            self.update_activity(data)
            try:
                title, body = progress_text(data)
                self.render(title, body)
            except Exception:                          # noqa: BLE001
                # 文案生成失败不应影响寻色，保留上一帧
                pass
            return

        # 结束态：对齐 search_overlay.handle 的收尾分支。
        # 注意：这里只改浮窗的显示状态，业务收尾仍由 business.handle_event 负责。
        if kind in ('error', 'done', 'interrupted', 'wait_timeout', 'worker_failed'):
            self.state.set_running(False)
            self._stop_heartbeat()
            if kind in ('error', 'worker_failed'):
                message = data.get('message') or ''
                self.render('已停止', message or '本轮未能继续，请查看主窗口提示。')
                self.state.set_warn(True)
                self.state.set_stopped(True)
            elif kind == 'wait_timeout':
                self.render('等待超时', data.get('message') or '未在限定时间内识别到染色界面。')
                self.state.set_warn(True)
                self.state.set_stopped(True)
            elif kind == 'interrupted':
                self.render('已中断', data.get('message') or '自动操作已结束，请在游戏中查看当前颜色。')
                self.state.set_stopped(True)
            else:                                            # done
                self.render('本轮结束', data.get('message') or
                            '全部目标达标，请在游戏内手动确认是否套用。')
                self.state.set_progress(1.0)
                self.state.set_stopped(True)
            return

        if kind == 'finished':
            # native 运行结束时直接收起浮窗
            if getattr(self, '_native_run', False):
                self.dismiss()
                return
            self.state.set_running(False)
            self._stop_heartbeat()
            return

        if kind in ('native_candidates', 'candidates'):
            self._candidate_data = data
            # batch_id 必须记下来，否则 chooseCandidate() 会因为
            # `self.batch_id is None` 直接 return，点击「选择此方案」毫无反应。
            self.batch_id = data.get('batch_id')
            self.default_candidate_id = data.get('default_id')
            self.state.set_candidates(self._candidate_rows(data))
            # 标题/正文与 search_overlay.show_candidates 对齐：
            # 有候选时要切到「本轮候选方案」，否则浮窗还停在等待态文案。
            if data.get('strategy') == 'native':
                self.render('本轮候选方案', '候选按区域优先级与色差排序')
            elif data.get('compromise_only') or data.get('family_unavailable'):
                self.render('自动定位最接近方案',
                            data.get('message') or '未找到满足所设目标的组合，正在定位最接近的妥协方案。')
            else:
                self.render('自动定位最佳方案',
                            '正在定位预测达标且剩余时间允许的方案。\n'
                            '完成后仍可选择其他方案，实际染色须在游戏内手动确认。')
            self.phase = 'positioning'
            return
        if kind in ('native_result', 'single_verified', 'screenshot_result'):
            self.state.set_running(False)
            return

    # -- QML 回调 ----------------------------------------------------------
    @Slot()
    def requestStop(self):
        if callable(self.stop_action):
            self.stop_action()

    @Slot()
    def requestRetry(self):
        if not self._retry_enabled or self._retry_pending or getattr(self, '_dismissed', False):
            return
        action = getattr(self.host, 'request_native_retry', None)
        if callable(action):
            action()

    @Slot(result=float)
    def opacity(self):
        return self._alpha

    @Slot(float)
    def setOpacity(self, value):
        self.set_opacity(value)

    @Slot()
    def commitPosition(self):
        self.save_position()

    @Slot()
    def toggleCollapse(self):
        self.state.set_collapsed(not self.state.collapsed)

    @Slot(str)
    def chooseCandidate(self, candidate_id):
        if self.select_candidate is None or self.batch_id is None:
            return
        self.select_candidate(self.batch_id, candidate_id)

    @Slot(int, int)
    def moveTo(self, x, y):
        """拖动：合并由 QML 的 pointer 事件节流，这里只做边界夹紧。"""
        if self._window is None:
            return
        scale = self._window.screen().devicePixelRatio() if self._window.screen() else 1.0
        size = (int(self._window.width() * scale), int(self._window.height() * scale))
        position = (int(x * scale), int(y * scale))
        area = work_area(self._window, position)
        px, py = clamp_position(position, area, size)
        self._window.setPosition(int(px / scale), int(py / scale))
        self._position = [int(px / scale), int(py / scale)]
        # 拖动结束后落库
        self.save_position()

    def _place(self, window):
        scale = window.screen().devicePixelRatio() if window.screen() else 1.0
        size = (int(window.width() * scale), int(window.height() * scale))
        position = (int(self._position[0] * scale), int(self._position[1] * scale))
        area = work_area(window, position)
        px, py = clamp_position(position, area, size)
        window.setPosition(int(px / scale), int(py / scale))