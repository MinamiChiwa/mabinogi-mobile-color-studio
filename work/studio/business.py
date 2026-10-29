"""业务核心：不依赖任何 GUI 框架。

## 为什么需要这个模块

原 `app.py` 把业务方法写在 `class App(ct.CTk)` 里，导致任何界面（包括 Qt）
只要复用这些方法，就必须 ``import app``，进而连带导入 ``customtkinter`` 并
执行 ``ct.set_appearance_mode`` / ``i18n.install_widgets(ct)`` 等 Tk 副作用。

本模块把**业务方法本身**搬出来，``App`` 与 ``QtHost`` 都从这个基类继承，
于是：

* 业务代码只有一份（不是复制两份）；
* Qt 入口不再需要 ``import customtkinter``；
* Tk 版 `app.py` 可以继续用同一批方法，行为不变。

## 边界

本模块**只**包含原来就在 `App` 里的业务方法，逐字搬运，未改写任何一行逻辑。
界面投影仍由宿主类（`app.App` 的 CTk 控件 / `qt_ui.host.QtHost` 的适配器）承担，
业务方法内部依旧是 ``self.status.configure(...)`` 这类调用。
"""
from __future__ import annotations

import json
import queue
import sys
import threading
from pathlib import Path

import i18n
from i18n import tr
from pathlib import Path as _Path

# 与原 app.py 一致：theme 在业务层以 ui_theme 的名字出现，只取色值常量。
# theme 本身不含 GUI 依赖（纯字典），不会把 Tk 拉起来。
import theme as ui_theme

# --- 与原 app.py 完全一致的模块级依赖 -------------------------------------
import platform_win  # noqa: F401  必须在截图模块之前建立物理像素感知
from app_data import resolve_data_directory
from engine import Runner
from vision import normalize_hex, rgb
from palette import allowed_colors, overview
from window_target import resolve_target, WindowTarget, activate_target_window
from result_history import describe_result, read_history, save_result
from ui_settings import read_settings, save_settings
from profile_store import read_profile, write_profile, canonical_profile, PresetStore
from strategy_defaults import migrate_strategy_defaults
from session_store import new_session_path, start_session_cleanup
from hotkeys import run_hotkeys
import numpy as np
from concurrent.futures import ThreadPoolExecutor

SERVER_OPTIONS = (('tw', '台服'), ('kr', '韩服'), ('jp', '日服'))
NATIVE_STRATEGY_LABEL = '精准寻色（读取内存，风险较高）'

APP_VERSION = '0.4.9'

# --- 外链与教程文案 -------------------------------------------------------
# 原来这两项在 ui_dialogs.py 里，但那个模块 import customtkinter，
# Qt 入口不能为了取一个地址把 Tk 拉起来，所以常量放在这本无 GUI 依赖的模块。
# ui_dialogs 仍保留同名常量，Tk 版行为不变。
GITHUB = 'https://github.com/MinamiChiwa/mabinogi-mobile-color-studio'
AFDIAN = 'https://afdian.com/a/minamichiwa'
PATREON = 'https://patreon.com/chiwaminami?utm_medium=unknown&utm_source=join_link&utm_campaign=creatorshare_creator&utm_content=copyLink'

TUTORIAL = [
('1. 选择服务器与窗口','选择台服、韩服或日服，再选择游戏窗口。窗口位置和大小请在开始前调整。'),
('2. 设置颜色要求','启用需要匹配的区域并设置目标色。精准 HEX 要求六位色码一致；相似颜色按设定色差匹配。优先级 1 最高。'),
('3. 选择寻色方式','截图寻色是默认方式，使用截图与鼠标操作。精准寻色会读取游戏内存，风险较高；它与颜色要求中的精准 HEX 是不同设置。'),
('4. 开始寻色','按 F8 或点击开始，按提示进入染色；色板已打开时也可启动。自动操作期间保持游戏在前台，避免移动鼠标或改变窗口。'),
('5. 查看结果','查看各区域的游戏实际色码与色差，再决定是否套用。标为上次实测的颜色是历史记录，请查看游戏当前画面。'),
('妥协选色','未全部达标时，按区域优先级兼顾整体色差、色相与饱和度；黑白灰沿用原有色差。精准 HEX 与相似颜色的达标条件不变。'),
('6. 停止或重试','F9 停止自动操作。F7 重新寻色（仅供测试）：缩小色板后继续本局搜索，沿用剩余时间，不额外使用染色剂。'),
('设置自动保存','颜色、匹配要求和优先级自动保存。保存方案可保留多套命名设置；编辑后载入即可使用。'),
]

PALETTE_POOL = ThreadPoolExecutor(max_workers=1)

# 与原 app.py 的模块级常量一致：色值同样取自 theme，不硬编码。
# 这两个值只被「清空读数」用到（把「实测颜色」重置成占位态）。
MUTED = ui_theme.color('muted')
ACCENT = ui_theme.color('accent')


def build_runner(emit, folder, strategy='screenshot', entry=None, entry_size=None):
    """与原 app.py 逐字一致。"""
    if strategy == 'native':
        from native_live.service import run_native_search
        return Runner(emit, folder, native_runner=run_native_search)
    if strategy == 'atlas':
        strategy = 'screenshot'
    if strategy not in ('screenshot', 'legacy'):
        raise ValueError('Unknown search strategy')
    from screenshot_live import run_screenshot_search
    return Runner(emit, folder, screenshot_runner=run_screenshot_search)


def build_preview(target, tolerance):
    """与原 app.py 的同名函数逐字一致（纯组合，不含新算法）。"""
    pixels = allowed_colors(target, tolerance)
    return pixels, overview(pixels)


def installation_root():
    from update_bootstrap import installation_root as _root
    return _root()


def data_directory():
    """与原 app.py 的 DATA 计算方式一致。"""
    from update_bootstrap import active_data_directory, installation_root as _root
    update_data = active_data_directory(_root()) if getattr(sys, 'frozen', False) else None
    return update_data or resolve_data_directory(
        (Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False)
         else Path(__file__).resolve().parent) / 'data')


DATA = data_directory()

i18n.language = i18n.normalize_language(
    read_settings(DATA / 'settings.json').get('language'))


class RuleSource:
    """区域规则的唯一实现。界面层（Tk 卡片 / Qt 卡片）都从这里取。

    原 `app.Card.rule` 的逐字搬运，保证送进引擎的规则字典完全一致。
    """

    def rule(self):
        if not self.enabled.get():
            return {'enabled': False, 'colors': [], 'exact': True, 'tolerance': 0}
        colors = ([normalize_hex(self.target.get())]
                  + [normalize_hex(x) for x in
                     self.alt.get().replace('，', ',').split(',') if x.strip()])
        return {'enabled': True, 'colors': colors,
                'exact': self.mode.get() == '精准 HEX',
                'tolerance': self.tolerance.get()}


class Business:
    """业务方法集合。宿主类（CTk / Qt）提供 ``self.<控件>`` 即可运行。

    这里的方法体来自原 `app.App`，逐字搬运。
    """

    # ------------------------------------------------------------------
    # 运行控制
    # ------------------------------------------------------------------
    def go(self, mode='search', activate=False):
        if getattr(self, '_update_health_pending', False):
            return
        if hasattr(self, 'updater'):
            if self.updater.service.state in ('installing', 'waiting_for_exit'):
                return
            self.updater.set_busy(True)
        if self.busy:
            self.status.configure(text='任务已启动，正在等待或寻色；按 F9 停止。')
            return
        if self.picking:
            return
        for c in self.cards:
            c.set_session_available(True)
        self.region_note.grid_remove()
        try:
            rules = [dict(c.rule(), priority=c.priority.get()) for c in self.cards]
            if not getattr(self, '_profile_read_failed', False) or getattr(self, '_autosave_job', None) is not None:
                self.flush_autosave()
            if mode == 'search' and not any(r['enabled'] for r in rules):
                raise ValueError('请至少启用一个颜色区域。')
        except ValueError as e:
            self.status.configure(text=str(e))
            return
        strategy = self.search_strategy.get() if mode == 'search' else 'legacy'
        runtime_strategy = strategy
        target = self.selected_window
        self.active_rules = rules
        self._native_candidate_batch = None
        self._native_candidate_closed = False
        self._retry_enabled = False
        self._bound_target = None
        self.active_mode = mode
        self.busy = True
        self.start.configure(state='disabled')
        self.status.configure(text='正在识别游戏界面…')
        session_root = DATA / 'sessions'
        start_session_cleanup(session_root)
        folder = new_session_path(session_root)
        try:
            self.runner = build_runner(lambda k, d: self.q.put((k, d)), folder, strategy)
        except (ValueError, RuntimeError) as exc:
            self.busy = False
            self.start.configure(state='normal')
            self.status.configure(text=tr(str(exc)))
            return
        self.clear_run_readings()
        if mode == 'search':
            try:
                if self.overlay is None:
                    self.overlay = self._make_overlay()
                self.overlay.begin(rules, passive=strategy in ('native', 'screenshot'))
            except Exception:
                self.set_detail('浮窗暂不可用，寻色状态请查看主窗口。')
        threading.Thread(target=self.runner.launch,
                         args=(rules, mode, False, activate, target),
                         kwargs={'strategy': runtime_strategy, 'server': self.server.get()},
                         daemon=True).start()

    def stop(self, source='ui_button'):
        if self.runner:
            request = getattr(self.runner, 'request_stop', None)
            if callable(request):
                request(source)
            else:
                from run_stop import request_stop
                request_stop(self.runner.stop, source)
        self._native_candidate_closed = True
        self._retry_enabled = False
        self.status.configure(text='正在停止并释放鼠标…' if self.busy else '已停止自动染色，可重新开始。')
        if self.overlay is not None:
            self.overlay.dismiss()

    def finish_run(self):
        stopped = self.runner is not None and self.runner.stop.is_set()
        self.busy = False
        self.runner = None
        self._retry_enabled = False
        self._bound_target = None
        self.start.configure(state='normal')
        if stopped:
            self.status.configure(text='已停止自动染色，可重新开始。')
            if self.overlay is not None:
                self.overlay.dismiss()

    def select_candidate(self, batch_id, candidate_id):
        if self.runner:
            self.runner.choose_candidate(batch_id, candidate_id)

    def request_native_retry(self):
        if (self.runner and self.busy and self.search_strategy.get() in ('native', 'screenshot')
                and getattr(self, '_retry_enabled', False)):
            target = self._bound_target or self.selected_window
            try:
                if target is not None and not activate_target_window(target):
                    self.set_detail(tr('请先返回游戏窗口，再点击重试。'))
                    return
            except (OSError, RuntimeError):
                self.set_detail(tr('请先返回游戏窗口，再点击重试。'))
                return
            self._retry_enabled = False
            if self.overlay is not None:
                self.overlay.mark_retry_requested()
            self.runner.request_retry()

    # ------------------------------------------------------------------
    # 事件轮询
    # ------------------------------------------------------------------
    def tick(self):
        if self.__dict__.get('_closing', False):
            return
        updater = self.__dict__.get('updater')
        if updater is not None:
            updater.set_busy(self.busy or self.__dict__.get('picking', False)
                             or self.__dict__.get('_window_selecting', False)
                             or self.__dict__.get('_color_selecting', False))
        try:
            for _ in range(50):
                if self.q.empty():
                    break
                k, d = self.q.get()
                try:
                    if self.overlay is not None:
                        self.overlay.handle(k, d)
                except Exception:
                    self.report_callback_exception(*sys.exc_info())
                try:
                    self.handle_event(k, d)
                except Exception:
                    self.report_callback_exception(*sys.exc_info())
        finally:
            if not self.__dict__.get('_closing', False):
                self.after(60, self.tick)

    def hotkey_loop(self):
        keys = [(1, 0x77), (2, 0x78), (3, 0x76)]
        if not getattr(sys, 'frozen', False):
            keys.append((5, 0x75))

        def receive(kind, data):
            if kind == 'hotkey' and data['id'] == 2:
                runner = self.runner
                data = dict(data, target_run_token=runner.run_token if runner is not None else None)
                if runner is not None:
                    source = 'hotkey_' + data.get('source', 'unknown')
                    request = getattr(runner, 'request_stop', None)
                    if callable(request):
                        request(source)
                    else:
                        from run_stop import request_stop
                        request_stop(runner.stop, source)
            self.q.put((kind, data))

        run_hotkeys(platform_win.u, __import__('ctypes'), platform_win.W,
                    self._hotkeys_stop, receive, keys)

    # ------------------------------------------------------------------
    # 结果展示
    # ------------------------------------------------------------------
    def display_colors(self, row):
        """Paint actual readings without replacing progress or saving history."""
        for index, c in enumerate(self.cards):
            if not getattr(c, 'session_available', True):
                continue
            if index >= len(row['regions']):
                c.best_label.configure(text='实测颜色  —', fg_color='#28364A', text_color=MUTED)
                continue
            r = row['regions'][index]
            delta = r['delta']
            color = r['color']
            text = (f'{color or "—"} · ΔE {delta:.2f}' if delta is not None else
                    '实测颜色  —' if color is None and r['enabled'] else f'{color or "—"} · 未参与匹配')
            c.best_label.configure(
                text=text, fg_color=color or '#28364A',
                text_color='#17202B' if color and sum(rgb(color)) > 430 else 'white')

    def display_readings(self, colors):
        if self.active_rules:
            self.display_colors(describe_result(colors, self.active_rules))

    # -- 提示框：业务层只声明「要提示什么」--------------------------------
    def show_notice(self, kind, title, message):
        """弹出提示框。

        默认实现仍用 tkinter.messagebox —— Tk 版（``app.App``）没有覆写它，
        行为与改动前逐字一致。Qt 版在 ``QtHost`` 里覆写成自绘对话框，
        因此业务层本身不再 ``import tkinter``。
        """
        from tkinter import messagebox
        if kind == 'error':
            messagebox.showerror(title, message, parent=self)
        else:
            messagebox.showinfo(title, message, parent=self)

    def clear_run_readings(self):
        self.best_summary = None
        for card in self.cards:
            card.current.configure(text='当前颜色  —')
            card.best_label.configure(text='实测颜色  —', fg_color='#28364A', text_color=MUTED)

    def display_best(self, row):
        self.best_summary = row
        self.display_colors(row)
        if row['maximum'] is not None:
            if row.get('outcome') == 'compromise':
                prefix = '妥协方案（未达目标） · 本次结果'
            else:
                prefix = '本次结果' if row.get('outcome') else '最佳组合'
            self.set_detail(tr(prefix) + tr(' · 最大色差 ΔE ') +
                            f'{row["maximum"]:.2f}' + tr(' / 平均 ') +
                            f'{row["average"]:.2f}' + tr(' · 色差越小越接近目标'))

    # ------------------------------------------------------------------
    # 方案与设置
    # ------------------------------------------------------------------
    def current_profile(self):
        return dict(schema=1,
                    regions=[{key: getattr(c, key).get() for key in
                              ('enabled', 'target', 'alt', 'mode', 'tolerance')} for c in self.cards],
                    priority_order=sorted(range(3), key=lambda i: self.cards[i].priority.get()),
                    search_strategy=self.search_strategy.get())

    def apply_profile(self, profile, *, persist=True):
        if self.busy:
            raise ValueError('请先停止寻色，再载入方案。')
        profile = canonical_profile(profile)
        self._loading_profile = True
        try:
            for card, row in zip(self.cards, profile['regions']):
                for key in ('enabled', 'target', 'alt', 'mode', 'tolerance'):
                    getattr(card, key).set(row[key])
                card.change_mode()
            for rank, index in enumerate(profile['priority_order'], 1):
                self.cards[index].priority.set(rank)
                self.cards[index].priority_menu.set(str(rank))
            self.search_strategy.set(profile['search_strategy'])
            self.refresh_language()
        finally:
            self._loading_profile = False
        if persist and not self.flush_autosave():
            raise OSError('设置未能自动保存，请检查数据目录是否可写。')

    def set_card_priority(self, index, rank):
        if self.busy:
            self.cards[index].priority_menu.set(str(self.cards[index].priority.get()))
            return
        previous = self.cards[index].priority.get()
        for card in self.cards:
            if card.index != index and card.priority.get() == rank:
                card.priority.set(previous)
                card.priority_menu.set(str(previous))
        self.cards[index].priority.set(rank)
        self.cards[index].priority_menu.set(str(rank))
        self.schedule_autosave()

    def schedule_autosave(self, *_):
        if getattr(self, '_update_health_pending', False):
            return
        if getattr(self, '_loading_profile', False):
            return
        job = getattr(self, '_autosave_job', None)
        if job is not None:
            try:
                self.after_cancel(job)
            except Exception:
                pass
        self._autosave_job = self.after(300, self.flush_autosave)

    def flush_autosave(self):
        if getattr(self, '_update_health_pending', False):
            return True
        job = getattr(self, '_autosave_job', None)
        if job is not None:
            try:
                self.after_cancel(job)
            except Exception:
                pass
        self._autosave_job = None
        try:
            write_profile(DATA / 'profile.json', self.current_profile())
            self._profile_read_failed = False
            return True
        except (OSError, ValueError):
            self.set_detail(tr('设置未能自动保存，请检查数据目录是否可写。'))
            return False

    def load(self):
        try:
            migrated = getattr(self, '_strategy_defaults', {}).get('profile')
            profile = (canonical_profile(migrated) if migrated is not None
                       else read_profile(DATA / 'profile.json',
                                         search_strategy=self.search_strategy.get()))
        except (OSError, ValueError):
            from profile_store import default_profile
            profile = default_profile()
            profile['search_strategy'] = self.search_strategy.get()
            self._profile_read_failed = True
            self.set_detail(tr('当前设置无法读取，原文件已保留。'))
        self.apply_profile(profile, persist=False)

    # ------------------------------------------------------------------
    # 服务器 / 策略 / 语言
    # ------------------------------------------------------------------
    def change_server(self, value):
        if (self.busy or getattr(self, '_update_health_pending', False) or
                hasattr(self, 'updater') and self.updater.service.state in ('installing', 'waiting_for_exit')):
            self.server_menu.set(str(tr(dict(SERVER_OPTIONS)[self.server.get()])))
            return
        selected = next((server for server, label in SERVER_OPTIONS if str(tr(label)) == value), None)
        if selected is None:
            return
        picker = getattr(self, '_window_picker', None)
        if picker is not None and picker.winfo_exists():
            picker.destroy()
        self.server.set(selected)
        self.selected_window = None
        self._bound_target = None
        save_settings(DATA / 'settings.json', server=selected)
        self.refresh_window_label()
        self.status.configure(text='服务器已切换，窗口检测已更新。')

    def change_search_strategy(self, value):
        if getattr(self, '_update_health_pending', False):
            return
        if self.busy:
            self.strategy_menu.set(str(tr(NATIVE_STRATEGY_LABEL
                                         if self.search_strategy.get() == 'native' else '截图寻色')))
            return
        strategy = ('native' if value in (str(tr(NATIVE_STRATEGY_LABEL)), str(tr('精准寻色')))
                    else 'screenshot')
        self.search_strategy.set(strategy)
        save_settings(DATA / 'settings.json', search_strategy=strategy)
        self.refresh_language()
        self.schedule_autosave()

    def change_language(self, value):
        i18n.set_language(value)
        if not getattr(self, '_update_health_pending', False):
            save_settings(DATA / 'settings.json', language=value)

    def refresh_window_label(self):
        target = self.selected_window
        if target is None:
            try:
                title = resolve_target(server=self.server.get()).title
            except RuntimeError:
                title = tr('未检测到唯一窗口')
            text = tr('自动检测') + ' · ' + title
        else:
            text = tr('游戏窗口 · ') + target.title
        self.window_button.configure(text=text if len(text) <= 34 else text[:31] + '…')

    def refresh_server_label(self):
        self.server_menu.configure(values=[str(tr(label)) for _, label in SERVER_OPTIONS])
        self.server_menu.set(str(tr(dict(SERVER_OPTIONS)[self.server.get()])))

    # ------------------------------------------------------------------
    # 区域布局
    # ------------------------------------------------------------------
    def apply_region_layout(self, data):
        from dye_regions import region_count
        count = region_count(data['region_count'])
        rules = data.get('rules')
        if not isinstance(rules, (list, tuple)) or len(rules) != count:
            raise ValueError('Target rules do not match the actual dye regions')
        self.active_rules = json.loads(json.dumps(rules))
        self.active_region_count = count
        for index, card in enumerate(self.cards):
            card.set_session_available(index < count)
        if count == 2:
            self.region_note.configure(text='已识别 2 个染色区域，区域 3 本局不可用。')
            self.region_note.grid()
        else:
            self.region_note.grid_remove()

    # ------------------------------------------------------------------
    # 事件分发（纯业务逻辑，未改写）
    # ------------------------------------------------------------------
    def handle_event(self,k,d):
        if k=='update':self.update_ui.handle(d)
        elif k=='hotkey':
            if d['id']==1:self.go(activate=True)
            elif d['id']==2:
                if self.runner is None or d.get('target_run_token')!=self.runner.run_token:return
                self.stop(source='hotkey_'+d.get('source','unknown'))
            elif d['id']==3:self.request_native_retry()
            elif d['id']==5:self.go('recovery_test')
        elif k=='hotkey_status':
            names={1:'F8',2:'F9',3:'F7',5:'F6'}
            failed=[names[i] for i in d['failed']]
            text=(tr('快捷键已就绪：F8 开始 / F7 重试 / F9 停止') if not failed else
                  tr('全局注册不可用：')+', '.join(failed)+tr('；F9 仍通过轮询停止，其他操作请使用按钮。'))
            self.footer.configure(text=text)
        elif k=='window_bound':
            if d.get('pid') is not None:self._bound_target=WindowTarget(int(d['hwnd']),int(d['pid']),d['title'])
            self.set_detail(tr('正在识别窗口：')+d['title'])
            prefix=tr('自动检测')+' · ' if self.selected_window is None else tr('游戏窗口 · ')
            label=prefix+d['title']
            self.window_button.configure(text=label if len(label)<=34 else label[:31]+'…')
        elif k=='region_layout':self.apply_region_layout(d)
        elif k=='targets':
            for c,color in zip(self.cards,d['colors']):
                c.enabled.set(True);c.target.set(color);c.alt.set('')
            self.flush_autosave()
        elif k in ('scene','match','restore_action','native_colors'):
            for i,(c,color) in enumerate(zip(self.cards,d.get('colors',[]))):
                inactive=self.active_rules is not None and not self.active_rules[i]['enabled']
                c.current.configure(text='当前颜色  '+(color or ('未参与匹配' if inactive else '读取失败')))
            self.display_readings(d.get('colors',[]))
            if k=='scene':self.status.configure(text=f'正在寻色 · 游戏剩余 {d.get("seconds") or "—"} 秒')
            elif k=='restore_action':self.status.configure(text=f'正在恢复最佳颜色 · 游戏剩余 {d.get("seconds") or "—"} 秒')
        elif k=='waiting':
            self.status.configure(text=tr('等待染色界面') if d.get('seconds') is None else tr('等待染色界面 · 剩余 ')+str(d['seconds'])+tr(' 秒'))
            self.set_detail(tr(d['message']))
        elif k in ('atlas_progress','single_progress','native_progress','screenshot_progress'):
            from ui_progress import progress_text
            title,body=progress_text(d)
            self.status.configure(text=tr(title));self.set_detail(tr(body))
            if k in ('native_progress','screenshot_progress') and d.get('stage')=='refinement' and d.get('verified') and d.get('screenshot_verified'):
                for card,color in zip(self.cards,d.get('current_colors') or []):
                    card.current.configure(text=tr('当前颜色  ')+(color or tr('读取失败')))
                self.display_readings(d.get('current_colors') or [])
        elif k=='native_retry_available':
            from native_status import retry_reason_text
            self._retry_enabled=bool(d.get('enabled'))
            if d.get('verified') and d.get('screenshot_verified'):
                for card,color in zip(self.cards,d.get('current_colors') or []):
                    card.current.configure(text=tr('当前颜色  ')+(color or tr('读取失败')))
                self.display_readings(d.get('current_colors') or [])
            if d.get('waiting_for_retry'):
                self.status.configure(text=tr('本轮寻色已完成'))
                self.set_detail(tr('可按 F7 或点击浮窗重试；剩余时间不足时保留当前颜色。' if d.get('enabled')
                    else retry_reason_text(d.get('reason'))))
        elif k=='native_retry_reset':
            self._retry_enabled=False
            status=d.get('status')
            if status=='zooming':
                self.status.configure(text=tr('正在重试'))
                self.set_detail(tr('正在缩小画板并重新搜索。'))
            elif status=='searching':
                self.status.configure(text=tr('重新搜索目标颜色'))
                self.set_detail(tr('沿用本局剩余时间重新寻色；F9 可停止。'))
            elif status=='rejected':
                from native_status import retry_reason_text
                self.status.configure(text=tr('暂时无法重试'))
                self.set_detail(tr(retry_reason_text(d.get('reason'))))
        elif k in ('native_candidates','native_candidate_ready','native_candidate_selected','native_candidate_closed'):
            return
        elif k=='native_result':
            if d.get('region_count') in (2,3):self.apply_region_layout(d)
            from native_status import result_text,last_verified_display
            title,detail=result_text(d)
            self.status.configure(text=tr(title));self.set_detail(tr(detail))
            historical=last_verified_display(d)
            if historical is not None:
                for card,color,delta in zip(self.cards,historical['colors'],historical['deltas']):
                    text=tr(historical['label'])+'  '+color
                    if delta is not None:text+=f' · ΔE {delta:.2f}'
                    card.current.configure(text=text)
                self.display_readings(historical['colors'])
            else:
                for card,color in zip(self.cards,d.get('actual_colors') or [None]*3):
                    card.current.configure(text='当前颜色  '+(color or '读取失败'))
                self.display_readings(d.get('actual_colors') or [])
            if d.get('verified') and self.active_rules:
                try:
                    row=save_result(DATA/'history.json',d['actual_colors'],self.active_rules,
                        'matched' if d.get('accepted') else 'compromise' if d.get('outcome')=='compromise' else 'observed',
                        d.get('restored'),d.get('best_actual_colors'))
                    self.history=read_history(DATA/'history.json');self.display_best(row)
                except OSError:self.set_detail(tr('本轮结果未能保存，请检查程序文件夹是否可写。'))
        elif k in ('single_verified','screenshot_result'):
            from native_status import last_verified_display
            historical=last_verified_display(d)
            colors=historical['colors'] if historical else d.get('actual_colors') or [None]*3
            for i,(card,color) in enumerate(zip(self.cards,colors)):
                disabled=self.active_rules is not None and not self.active_rules[i]['enabled']
                label=tr(historical['label'])+'  ' if historical else tr('当前颜色  ')
                card.current.configure(text=label+(color or tr('未参与匹配' if disabled else '读取失败')))
            self.display_readings(colors)
            from ui_progress import single_result_presentation
            if k=='screenshot_result':
                from screenshot_presentation import result_text
                title,detail=result_text(d)
            else:title,detail=single_result_presentation(d)
            self.status.configure(text=tr(title))
            self.set_detail(tr(detail))
            if d.get('verified') and self.active_rules:
                try:
                    row=save_result(DATA/'history.json',d['actual_colors'],self.active_rules,
                        'matched' if d.get('accepted') else 'compromise',
                        d.get('restored'),d.get('best_actual_colors'))
                    self.history=read_history(DATA/'history.json');self.display_best(row)
                except OSError:self.set_detail(tr('本轮结果未能保存，请检查程序文件夹是否可写。'))
            if k=='screenshot_result' and d.get('best_current') is False:
                self.set_detail(tr(detail))
        elif k=='atlas_status':
            self.status.configure(text=tr('自动染色'))
            self.set_detail(tr(d.get('message','')))
        elif k=='atlas_ready':self.status.configure(text=tr('本局颜色板质量门槛通过，正在准备自动最佳方案。'))
        elif k in ('atlas_default_verified','atlas_verified'):
            colors=d.get('actual_colors',d.get('colors',[]))
            for card,color in zip(self.cards,colors):card.current.configure(text='当前颜色  '+(color or '读取失败'))
            self.display_readings(colors)
            self.status.configure(text='当前结果已达到所设目标，请在游戏内手动确认。' if d.get('accepted') else '当前结果未达到全部目标；请先查看妥协方案，再在游戏内手动确认是否套用。')
        elif k=='atlas_best_not_restored':
            for card,color in zip(self.cards,d.get('actual_colors') or [None]*3):
                card.current.configure(text='当前颜色  '+(color or '读取失败'))
            self.display_readings(d.get('actual_colors') or [])
            self.status.configure(text=tr('未能恢复先前最佳结果，请以游戏当前颜色为准。'))
        elif k=='atlas_default_unavailable':self.status.configure(text=tr(d.get('message','剩余时间不足，未发送定位操作。')))
        elif k=='atlas_invalidated':self.status.configure(text=tr(d.get('message','颜色板质量未达标，未发布候选。')))
        elif k=='atlas_choice_rejected':self.status.configure(text=tr(d.get('message','剩余时间不足，保持自动最佳方案。')))
        elif k=='atlas_selection_expired':self.status.configure(text=tr('未选择其他方案，保持自动最佳方案。'))
        elif k in ('wait_timeout','interrupted'):
            self.status.configure(text=tr(d['message']))
            if not (self.runner is not None and self.runner.stop.is_set()):
                self.after(100,lambda m=d['message']:self.show_notice('info',tr('流程已中断'),tr(m)))
        elif k=='action':self.set_detail('正在调整色板，持续寻找更接近的颜色…')
        elif k in ('explore','restoring','magnifying','restore_fallback','input_recheck','activation'):self.set_detail(d['message'])
        elif k=='best':
            if self.active_rules:self.display_best(describe_result(d['colors'],self.active_rules))
        elif k in ('error','done'):
            self.status.configure(text=d.get('message',''))
            if k=='error':
                self.after(100,lambda m=d.get('message',''):self.show_notice('error',tr('流程已中断'),tr(m)))
            elif not d.get('popup') and getattr(self,'active_mode','search')=='search':
                self.after(100,lambda m=d.get('message',''):self.show_notice('info',tr('流程已中断'),tr(m)))
            for c,color in zip(self.cards,d.get('colors',[])):c.current.configure(text='当前颜色  '+(color or '读取失败'))
            self.display_readings(d.get('colors',[]))
            if d.get('popup'):
                if self.active_rules:
                    try:
                        row=save_result(DATA/'history.json',d.get('colors',[]),self.active_rules,d.get('outcome'),d.get('restored'),d.get('best_colors'))
                        self.history=read_history(DATA/'history.json');self.display_best(row)
                    except OSError:self.set_detail('本轮结果未能保存，请检查程序文件夹是否可写。')
                message=d['message']+'\n\n当前颜色：'+' / '.join(c or '未识别' for c in d.get('colors',[]))
                self.after(100,lambda m=message,o=d.get('outcome'):self.show_notice('info',tr('流程完成 · '+('妥协结果' if o=='compromise' else '目标达标')),tr(m)))
        elif k=='worker_failed':
            self.status.configure(text=tr('工具内部错误，已停止'))
            self.set_detail(tr('本轮未继续发送操作，详细异常已写入诊断记录。'))
        elif k=='finished':self.finish_run()
