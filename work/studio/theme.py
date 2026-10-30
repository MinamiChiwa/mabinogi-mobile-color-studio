"""V7 设计令牌：单一颜色来源，同时支持深色 / 浅色两套。

本模块只提供颜色、圆角、字号等**展示层**常量，不含任何业务逻辑。
业务代码通过 `theme.color('bg')` 这类语义名取值，不直接写字面量。

设计基线见 docs/design/ui-spec-v7.md。
"""
from __future__ import annotations

APPEARANCES = ('dark', 'light')
DEFAULT_APPEARANCE = 'dark'

# ---------------------------------------------------------------------------
# 语义色板：每个令牌给出 (dark, light) 两个值
# ---------------------------------------------------------------------------
_TOKENS = {
    # 背景层级
    'bg':           ('#17181D', '#F2F3F5'),
    'panel':        ('#191A20', '#FFFFFF'),
    'panel_alt':    ('#1F212A', '#F7F8FA'),
    'field':        ('#18191F', '#FFFFFF'),
    'pop':          ('#1F212A', '#FFFFFF'),

    # 描边
    'line':         ('#23252B', '#E1E3E8'),
    'line_soft':    ('#202228', '#EDEFF3'),
    'field_line':   ('#2A2C33', '#D6D9E0'),

    # 文字
    'text':         ('#E3E5EA', '#1B1D22'),
    'text_2':       ('#9BA1AD', '#545A66'),
    'muted':        ('#6F7480', '#6E7480'),
    'faint':        ('#5C626F', '#8A909C'),

    # 语义色
    'accent':       ('#5DC264', '#2E9E3F'),
    'accent_soft':  ('#2F4C36', '#CDEBCF'),
    'accent_hover': ('#70CF77', '#3BB24C'),
    'on_accent':    ('#10200F', '#FFFFFF'),
    'warn':         ('#D8B268', '#A97C1E'),
    'danger':       ('#D08A82', '#C0554C'),

    # 按钮
    'btn':          ('#262933', '#FFFFFF'),
    'btn_hover':    ('#2D313B', '#F0F2F5'),
    'btn_line':     ('#343841', '#D6D9E0'),
    'btn_text':     ('#9BA1AD', '#3C424D'),

    # 读数占位（"无色可显示"时的中性底，不是主题色）
    'placeholder':  ('#28364A', '#E6E9EF'),

    # 启用态整卡染色（按用户要求保留）
    'card_on':      ('#192D35', '#E8F5EC'),
    'card_off':     ('#151B25', '#F7F8FA'),
    'card_on_line': ('#5DC264', '#2E9E3F'),

    # ---- 以下是 ui-spec-v7.md 4.1 / 4.2 明确要求、但之前缺失的令牌 ----
    'panel_line':   ('#22242B', '#E1E3E8'),   # 面板外框（区域卡之上的容器）
    'pop_line':     ('#32353F', '#D6D9E0'),   # 浮层外框
    'muted_2':      ('#9BA1AD', '#545A66'),   # 正文说明、次级按钮文字
    'green':        ('#5DC264', '#2E9E3F'),   # =accent，语义别名
    'green_soft':   ('#2F4C36', '#CDEBCF'),   # =accent_soft
    'amber':        ('#D8B268', '#A97C1E'),   # =warn

    # 状态与描边的补充
    'track':        ('#2A2C33', '#D6D9E0'),   # 滑杆未完成段
    'track_off':    ('#141519', '#E1E3E8'),   # 进度槽
    'selected':     ('#1D2620', '#DDF2E1'),   # 候选卡已选底
    'card_open':    ('#1C1D24', '#EDEFF3'),   # 卡片浮窗打开时的底
    'card_open_line': ('#2E3139', '#C9CCD4'), # 卡片浮窗打开时的描边
}

_RADIUS = {'card': 10, 'panel': 10, 'dialog': 12, 'control': 6, 'chip': 5, 'primary': 7}

# ---------------------------------------------------------------------------
# 字号（ui-spec-v7.md 5.2）：role -> (size, weight)
# ---------------------------------------------------------------------------
_FONTS = {
    'brand':      (16, 650),   # 品牌标题
    'region':     (15, 600),   # 区域标题
    'overlay':    (15, 600),   # 悬浮窗标题
    'dialog':     (14, 600),   # 对话框标题
    'hex':        (14, 400),   # HEX 输入（Mono）
    'label':      (13, 400),   # 字段标签
    'body':       (12.5, 400), # 正文说明
    'body_sm':    (12, 400),
    'button':     (12, 500),
    'button_lg':  (13, 650),   # 主按钮
    'status':     (11, 550),   # 状态主行
    'row':        (11, 400),   # 悬浮窗候选行（Mono）
    'note':       (10.5, 400), # 辅助说明
    'meta':       (10, 400),
    'fine':       (9.5, 400),
    'footnote':   (9, 400),    # 页脚、日志
    'badge':      (9.5, 500),  # 徽标
}

# ---------------------------------------------------------------------------
# 间距与动效（ui-spec-v7.md 6.1 / 第 8 节 与原型 transition）
# ---------------------------------------------------------------------------
_MOTION = {
    'fast': 120,     # .12s  hover 微反馈
    'base': 150,     # .15s  颜色/边框
    'mid': 180,      # .18s  开关、卡片底色
    'slow': 240,     # .24s  浮层进场
    'timer': 350,    # .35s  进度条宽度
    'hold': 900,     # 选择候选后先高亮再进复核
}


class _Theme:
    """轻量主题对象；`appearance` 决定取哪一列。"""

    def __init__(self, appearance: str = DEFAULT_APPEARANCE):
        self.appearance = appearance if appearance in APPEARANCES else DEFAULT_APPEARANCE

    # -- 查询 ---------------------------------------------------------------
    def color(self, name: str) -> str:
        pair = _TOKENS.get(name)
        if pair is None:
            raise KeyError(f'未知主题令牌: {name}')
        return pair[0] if self.appearance == 'dark' else pair[1]

    def radius(self, name: str) -> int:
        return _RADIUS[name]

    def font(self, name: str):
        """返回 (size, weight)。"""
        return _FONTS[name]

    def motion(self, name: str) -> int:
        """返回毫秒时长，供 QML 的 NumberAnimation 使用。"""
        return _MOTION[name]

    def is_dark(self) -> bool:
        return self.appearance == 'dark'

    # -- 切换 ---------------------------------------------------------------
    def set_appearance(self, appearance: str) -> bool:
        """返回是否真的发生了变化，供调用方决定要不要重绘。"""
        if appearance not in APPEARANCES or appearance == self.appearance:
            return False
        self.appearance = appearance
        return True

    # -- 便捷属性（只读） ---------------------------------------------------
    def __getattr__(self, item):
        # 允许 theme.bg / theme.text 这类直读；未命中则抛错，避免静默返回 None
        if item in _TOKENS:
            return self.color(item)
        raise AttributeError(item)


# 进程级单例：UI 层统一从这里取色
theme = _Theme()

# 别名，避免 `theme.text` 常被误写成模块属性（模块与单例同名）
palette = theme


def color(name: str) -> str:
    return theme.color(name)


def radius(name: str) -> int:
    return theme.radius(name)


def font(name: str):
    return theme.font(name)


def motion(name: str) -> int:
    return theme.motion(name)


def apply_appearance(appearance: str) -> bool:
    return theme.set_appearance(appearance)


def available_tokens() -> tuple:
    return tuple(_TOKENS)