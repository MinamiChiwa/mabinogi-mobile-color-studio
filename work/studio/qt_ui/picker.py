"""目标色浮窗：9×5 色域 + 最近使用 + 常用色 + HSL 精调。

**边界说明**：本模块只产出"用户点选的颜色"和"当前色的 HSL 回填"，
不参与寻色判定。HSL↔HEX 换算是展示层的标准换算，与寻色引擎的
Lab/ΔE 计算无关（后者在 `color_matching.py`，本模块不引用、不修改）。
"""
from __future__ import annotations

import colorsys

from PySide6.QtCore import Property, QObject, Signal, Slot

# 常用色 12 个（ui-spec 7.4）
COMMON_COLORS = [
    '#000000', '#FFFFFF', '#7F7F7F', '#8E0126',
    '#A3122E', '#7A0520', '#3E5A3A', '#2F4C36',
    '#1E3A5F', '#2B5C8A', '#8A6D3B', '#5A4A6B',
]


def hex_to_rgb(value):
    value = value.lstrip('#')
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(r, g, b):
    return '#%02X%02X%02X' % (
        max(0, min(255, int(round(r)))),
        max(0, min(255, int(round(g)))),
        max(0, min(255, int(round(b)))))


def hex_to_hsl(value):
    r, g, b = (c / 255.0 for c in hex_to_rgb(value))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return round(h * 360) % 360, round(s * 100), round(l * 100)


def hsl_to_hex(h, s, l):
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360.0, l / 100.0, s / 100.0)
    return rgb_to_hex(r * 255, g * 255, b * 255)


def is_neutral(value):
    """饱和度 < 0.06 视为中性色（ui-spec 7.4）。"""
    r, g, b = (c / 255.0 for c in hex_to_rgb(value))
    _h, _l, s = colorsys.rgb_to_hls(r, g, b)
    return s < 0.06


class PickerState(QObject):
    """浮窗数据源。所有写入只影响显示。"""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._target = '#202020'
        self._h = 0
        self._s = 0
        self._l = 12
        self._grid = []
        self._recent = []
        self._tolerance = 8
        self._exact = True
        self._available = True

    # -- 只读投影 -----------------------------------------------------------
    def _emit(self):
        self.changed.emit()

    def _get_target(self):
        return self._target

    target = Property(str, _get_target, notify=changed)

    def _get_grid(self):
        return self._grid

    grid = Property('QVariantList', _get_grid, notify=changed)

    def _get_recent(self):
        return self._recent

    recent = Property('QVariantList', _get_recent, notify=changed)

    def _get_common(self):
        return COMMON_COLORS

    common = Property('QVariantList', _get_common, notify=changed)

    def _get_hue(self):
        return self._h

    hue = Property(int, _get_hue, notify=changed)

    def _get_sat(self):
        return self._s

    sat = Property(int, _get_sat, notify=changed)

    def _get_lig(self):
        return self._l

    lig = Property(int, _get_lig, notify=changed)

    def _get_neutral(self):
        return self._s == 0

    neutral = Property(bool, _get_neutral, notify=changed)

    def _get_available(self):
        return self._available

    available = Property(bool, _get_available, notify=changed)

    def _get_isExact(self):
        return self._exact

    isExact = Property(bool, _get_isExact, notify=changed)

    def _get_title(self):
        return '灰阶' if self._s == 0 else '选择目标色'

    title = Property(str, _get_title, notify=changed)

    # -- 写入 ---------------------------------------------------------------
    def set_context(self, target, *, tolerance=8, exact=True, available=True, recent=None):
        self._target = target.upper()
        self._tolerance = tolerance
        self._exact = exact
        self._available = available
        if recent is not None:
            self._recent = list(recent)[:6]
        self._sync_hsl()
        self._build_grid()
        self._emit()

    def _sync_hsl(self):
        self._h, self._s, self._l = hex_to_hsl(self._target)

    def _build_grid(self):
        """9 列 × 5 行：列 = ±12° 色相，行 = 明度；中央格强制等于目标色。"""
        h, s, l = self._h, self._s, self._l
        rows = []
        # 明度分档：目标亮度为中心，上下各两档
        levels = [max(4, l - 26), max(4, l - 13), l, min(96, l + 13), min(96, l + 26)]
        for r, lv in enumerate(levels):
            row = []
            for c in range(9):
                if r == 2 and c == 4:
                    row.append(self._target)
                    continue
                hue = (h + (c - 4) * 12) % 360
                row.append(hsl_to_hex(hue, s, lv))
            rows.append(row)
        self._grid = rows

    @Slot(int, int)
    def pick_cell(self, row, col):
        if not self._available:
            return
        try:
            value = self._grid[row][col]
        except (IndexError, KeyError):
            return
        self._target = value
        self._sync_hsl()
        self._build_grid()
        self._emit()

    @Slot(str)
    def pick_color(self, value):
        if not self._available or not value:
            return
        self._target = value.upper()
        self._sync_hsl()
        self._build_grid()
        self._emit()

    @Slot(int, int, int)
    def adjust(self, h, s, l):
        if not self._available:
            return
        self._h = max(0, min(360, h))
        self._s = max(0, min(100, s))
        self._l = max(0, min(100, l))
        self._target = hsl_to_hex(self._h, self._s, self._l)
        self._build_grid()
        self._emit()

    @Slot()
    def reset_sliders(self):
        self._sync_hsl()
        self._emit()

    # 三条滑杆的渐变端点（Property，QML 可直接下标取用）
    def _get_satTrack(self):
        return [hsl_to_hex(self._h, 0, self._l), hsl_to_hex(self._h, 100, self._l)]

    satTrack = Property('QVariantList', _get_satTrack, notify=changed)

    def _get_ligTrack(self):
        return ['#000000', hsl_to_hex(self._h, self._s, 50), '#FFFFFF']

    ligTrack = Property('QVariantList', _get_ligTrack, notify=changed)