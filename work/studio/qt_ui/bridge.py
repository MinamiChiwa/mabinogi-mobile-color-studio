"""QML 与业务层之间的唯一通道。

**这个类不做任何业务判断。** 每个槽函数只做三件事：

1. 把界面上的新值写进卡片变量（``VarShim``）；
2. 调用 `QtHost` / `business.Business` 的方法（``save`` / ``go`` / ``apply_profile`` …）；
3. 需要时把结果回写到 ``UiState``。
"""
from __future__ import annotations

import re

from PySide6.QtCore import QObject, Slot

import business as core


class Bridge(QObject):
    def __init__(self, host, state, parent=None):
        super().__init__(parent)
        self._host = host
        self._state = state

    # -- 通用 ---------------------------------------------------------------
    def _card(self, index):
        try:
            return self._host.cards[index]
        except (AttributeError, IndexError):
            return None

    @Slot(int)
    def toggleEnabled(self, index):
        card = self._card(index)
        if card is None:
            return
        card.enabled.set(not card.enabled.get())

    @Slot(int, int)
    def setPriority(self, index, rank):
        # 复用原方法：它会处理"同优先级互换"并把下拉框同步回去
        self._host.set_card_priority(index, rank)

    @Slot(int, str)
    def setTarget(self, index, value):
        card = self._card(index)
        if card is None:
            return
        card.target.set(value)

    @Slot(int, str)
    def setAlt(self, index, value):
        card = self._card(index)
        if card is None:
            return
        card.alt.set(value)

    @Slot(str, result=bool)
    def validHex(self, value):
        """HEX 是否合法。校验规则直接借用原模块，不在这里另立标准。"""
        text = (value or '').strip()
        if not text:
            return False
        try:
            core.normalize_hex(text)
            return True
        except (ValueError, IndexError, TypeError):
            return False

    @Slot(int, str)
    def removeAlt(self, index, value):
        """从替代色里去掉一个（按规范化后的 HEX 比较，逗号/全角逗号都认）。"""
        card = self._card(index)
        if card is None:
            return
        try:
            drop = core.normalize_hex(value)
        except (ValueError, IndexError, TypeError):
            return
        keep = []
        for part in re.split('[,，]', card.alt.get() or ''):
            part = part.strip()
            if not part:
                continue
            try:
                if core.normalize_hex(part) == drop:
                    continue
            except (ValueError, IndexError, TypeError):
                pass
            keep.append(part)
        card.alt.set(', '.join(keep))

    @Slot(int, bool)
    def setMode(self, index, exact):
        card = self._card(index)
        if card is None:
            return
        card.mode.set('精准 HEX' if exact else '相似颜色')
        card.change_mode()

    @Slot(int, float)
    def setTolerance(self, index, value):
        card = self._card(index)
        if card is None:
            return
        card.tolerance.set(float(value))
        card.change_mode()

    @Slot(int, result=bool)
    def openPicker(self, index):
        """打开色板浮层（不做 toggle）。返回是否真的打开。"""
        card = self._card(index)
        return bool(self._host.open_picker(card)) if card is not None else False

    @Slot(int, result=bool)
    def openAtlas(self, index):
        """打开目标色集合浮层。"""
        card = self._card(index)
        if card is None:
            return False
        self._host.open_atlas(card)
        return True

    @Slot()
    def closePicker(self):
        self._host.close_inline_picker()

    @Slot()
    def closeAtlas(self):
        self._host.close_atlas()

    @Slot(int, int, int)
    def pickerCell(self, index, row, col):
        card = self._card(index)
        if card is not None:
            self._host.pick_inline_cell(card, row, col)

    @Slot(int, str)
    def pickerColor(self, index, value):
        card = self._card(index)
        if card is not None:
            self._host.pick_inline_color(card, value)

    @Slot(int, int, int, int)
    def pickerSlide(self, index, h, sat, lig):
        card = self._card(index)
        if card is not None:
            self._host.apply_inline_picker(card, h, sat, lig)

    @Slot()
    def toggleAppearance(self):
        """浅色 / 深色切换。切完重绘全部卡片（颜色来自 theme）。"""
        import theme as ui_theme
        current = ui_theme.theme.appearance
        target = 'light' if current == 'dark' else 'dark'
        ui_theme.apply_appearance(target)
        self._state.set_appearance(target)
        # theme 变了，卡片的派生色（cardBg / cardLine）需要重算
        for i in range(3):
            card = self._card(i)
            if card is not None:
                card.refresh()
        self._host.refresh_language()

    @Slot(int)
    def eyedropper(self, index):
        card = self._card(index)
        if card is None:
            return
        self._host.pick_color(card.target.set)

    @Slot(int)
    def openViewer(self, index):
        card = self._card(index)
        if card is None:
            return
        pixels = getattr(card, '_palette_pixels', None)
        key = getattr(card, '_display_key', None)
        if pixels is None or not key:
            return
        from qt_ui.dialogs import open_palette_viewer
        open_palette_viewer(self._host, pixels, key[0])

    # -- 顶栏 / 工具栏 ------------------------------------------------------
    @Slot(str)
    def headerAction(self, key):
        handler = {
            'support': self._host.show_support,
            'tutorial': self._host.show_tutorial,
            'update': self._host.show_update_dialog,
            'github': self._host.open_github,
        }.get(key)
        if handler is not None:
            handler()

    @Slot(str)
    def toolbarAction(self, key):
        handler = {
            'save': self._host.save,
            'history': self._host.show_history,
        }.get(key)
        if handler is not None:
            handler()

    @Slot(str)
    def serverChanged(self, value):
        self._host.change_server(value)

    @Slot(str)
    def languageChanged(self, value):
        self._host.change_language(value)
        self._host.after_language_changed()

    # -- 运行 ---------------------------------------------------------------
    @Slot()
    def start(self):
        self._host.go(activate=True)

    @Slot()
    def stop(self):
        self._host.stop(source='main_stop_button')

    @Slot()
    def pickWindow(self):
        self._host.pick_window()

    @Slot(str)
    def strategyChanged(self, value):
        self._host.change_search_strategy(value)

    @Slot()
    def toggleLog(self):
        self._state.toggle_log()

    # -- 紧凑浮层：数据与动作 ------------------------------------------------
    #
    # 判断都在 window_target / profile_store / result_history 等模块，
    # 这里只负责把结果整理成 QML 能吃的列表。
    @Slot(result='QVariantList')
    def windowRows(self):
        """自动检测：列出可选游戏窗口。"""
        from window_target import list_windows, valid_target
        try:
            windows = list_windows()
        except RuntimeError:
            return []
        rows = []
        for w in windows:
            try:
                ready = bool(valid_target(w))
            except Exception:                          # noqa: BLE001
                ready = False
            rows.append({'hwnd': str(w.hwnd), 'title': w.title, 'ready': ready})
        return rows

    @Slot(str)
    def chooseWindow(self, hwnd):
        """浮层里点选窗口 → 交给宿主原有的选择流程。"""
        from window_target import list_windows, valid_target
        try:
            match = [w for w in list_windows() if str(w.hwnd) == str(hwnd)]
        except RuntimeError:
            match = []
        if not match or not valid_target(match[0]):
            self._state.apply(status='所选窗口已关闭，请重新选择游戏窗口。')
            return
        self._host.apply_window_target(match[0])

    @Slot(result='QVariantList')
    def presetRows(self):
        from profile_store import PresetStore
        try:
            rows = PresetStore(core.DATA / 'presets.json').rows()
        except (ValueError, OSError):
            return []
        out = []
        for row in rows:
            profile = row.get('profile') or {}
            regions = profile.get('regions') or []
            colors = ', '.join((r.get('target') or '') for r in regions if r.get('target'))
            out.append({'id': row['id'], 'name': row['name'],
                        'summary': colors[:40]})
        return out

    @Slot(str, result=str)
    def savePreset(self, name):
        """保存当前设置为方案；返回空字符串表示成功，否则返回错误文案。"""
        from profile_store import PresetStore
        try:
            store = PresetStore(core.DATA / 'presets.json')
            store.save(name, self._host.current_profile())
            return ''
        except ValueError as exc:
            return str(exc)
        except OSError:
            return '方案未能写入，请检查程序文件夹是否可写。'

    @Slot(str, result=str)
    def applyPreset(self, preset_id):
        from profile_store import PresetStore
        try:
            row = PresetStore(core.DATA / 'presets.json').get(preset_id)
            self._host.apply_profile(row['profile'])
            return ''
        except ValueError as exc:
            return str(exc)
        except OSError:
            return '方案无法读取，请保留文件并检查内容。'

    @Slot(str, result=str)
    def deletePreset(self, preset_id):
        from profile_store import PresetStore
        try:
            PresetStore(core.DATA / 'presets.json').delete(preset_id)
            return ''
        except (ValueError, OSError) as exc:
            return str(exc) or '删除失败。'

    @Slot(result='QVariantList')
    def historyRows(self):
        """寻色记录：与自绘大对话框同一份数据源。"""
        rows = []
        for row in getattr(self._host, 'history', []):
            regions = []
            for r in row.get('regions', []):
                regions.append({'region': r.get('region', 0),
                                'color': r.get('color') or '',
                                'delta': r.get('delta')})
            rows.append({'time': row.get('time', ''),
                         'outcome': row.get('outcome', ''),
                         'maximum': row.get('maximum'),
                         'average': row.get('average'),
                         'regions': regions})
        return rows

    @Slot(result='QVariantList')
    def tutorialRows(self):
        return [{'h': h, 'b': b} for h, b in core.TUTORIAL]

    @Slot(result='QVariantMap')
    def supportLinks(self):
        return {'afdian': core.AFDIAN, 'patreon': core.PATREON,
                'github': core.GITHUB, 'issues': core.GITHUB + '/issues'}

    @Slot(str)
    def openLink(self, url):
        if url:
            import webbrowser
            webbrowser.open(url)

    @Slot()
    def requestClose(self):
        self._host.close()
