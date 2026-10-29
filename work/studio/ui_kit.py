"""V7 组件工厂：统一按钮层级、下拉、状态点、分隔线的外观参数。

**只负责外观**：返回参数字典或已配置好的控件，不接管命令、不回写业务状态。
所有工厂都从 `theme` 取色，因此深浅色切换只需改 `theme` 的 appearance。

用法：
    ct.CTkButton(parent, **ui_kit.button('secondary'))
    ct.CTkButton(parent, **ui_kit.button('primary', text='开始'))
"""
from __future__ import annotations

import theme as _theme

# 按钮层级：全界面只允许一个 primary 处于可见状态
LEVELS = ('primary', 'secondary', 'ghost', 'danger')


def button(level: str = 'secondary', *, text: str = '', height: int = 30,
           width=None, font=None, **extra) -> dict:
    """返回 CTkButton 的构造参数。调用方自行装配 `command`。"""
    if level not in LEVELS:
        raise ValueError(f'未知按钮层级: {level}')
    t = _theme.palette

    if level == 'primary':
        style = dict(fg_color=t.accent_soft, hover_color=_hover(t.accent_soft, t.is_dark()),
                     text_color=t.text, border_width=1, border_color=_line(t.accent_soft, t.is_dark()))
    elif level == 'secondary':
        style = dict(fg_color=t.btn, hover_color=t.btn_hover,
                     text_color=t.btn_text, border_width=1, border_color=t.btn_line)
    elif level == 'ghost':
        style = dict(fg_color='transparent', hover_color=t.btn_hover,
                     text_color=t.muted, border_width=0)
    else:  # danger
        style = dict(fg_color='transparent', hover_color=t.btn_hover,
                     text_color=t.danger, border_width=1, border_color=t.danger)

    style.update(corner_radius=t.radius('control'), height=height)
    if text:
        style['text'] = text
    if width is not None:
        style['width'] = width
    if font is not None:
        style['font'] = font
    style.update(extra)
    return style


def select(*, width=None, height: int = 30, font=None, **extra) -> dict:
    """CTkOptionMenu 的外观参数。

    注意：CTkOptionMenu 不支持 `border_width` / `border_color`，
    因此这里不传，避免运行时报 ValueError。
    """
    t = _theme.palette
    style = dict(fg_color=t.field, button_color=t.btn, button_hover_color=t.btn_hover,
                 text_color=t.text, dropdown_fg_color=t.panel_alt,
                 dropdown_hover_color=t.btn_hover, dropdown_text_color=t.text,
                 corner_radius=t.radius('control'), height=height)
    if width is not None:
        style['width'] = width
    if font is not None:
        style['font'] = font
    style.update(extra)
    return style


def entry(*, height: int = 36, font=None, **extra) -> dict:
    """CTkEntry 的外观参数。"""
    t = _theme.palette
    style = dict(fg_color=t.field, border_color=t.field_line, text_color=t.text,
                 corner_radius=t.radius('control'), height=height)
    if font is not None:
        style['font'] = font
    style.update(extra)
    return style


def panel(**extra) -> dict:
    """卡片 / 面板容器。"""
    t = _theme.palette
    style = dict(fg_color=t.panel, corner_radius=t.radius('panel'),
                 border_width=1, border_color=t.line)
    style.update(extra)
    return style


def card(enabled: bool = True, available: bool = True, **extra) -> dict:
    """区域卡容器：**保留用户要求的启用态整卡染色**。

    启用 → 染色底 + 主色描边；未启用 → 深底 + 中性描边。
    """
    t = _theme.palette
    on = enabled and available
    style = dict(
        fg_color=t.card_on if on else t.card_off,
        border_width=2 if on else 1,
        border_color=t.card_on_line if on else t.line,
        corner_radius=t.radius('card'),
    )
    style.update(extra)
    return style


def slider(*, enabled: bool = True, **extra) -> dict:
    t = _theme.palette
    style = dict(
        progress_color=t.accent if enabled else '#45505F',
        button_color=t.accent if enabled else '#596273',
        button_hover_color=t.accent_hover if enabled else '#596273',
        fg_color='#303947' if enabled else '#3A485D',
    )
    style.update(extra)
    return style


def badge(kind: str = 'neutral', **extra) -> dict:
    """读数徽标：ok / warn / neutral。"""
    t = _theme.palette
    colors = {
        'ok': (t.accent, t.accent_soft),
        'warn': (t.warn, '#241F16' if t.is_dark() else '#FBF3E2'),
        'neutral': (t.muted, t.panel_alt),
    }
    fg, bg = colors.get(kind, colors['neutral'])
    style = dict(text_color=fg, fg_color=bg, corner_radius=t.radius('chip'))
    style.update(extra)
    return style


# ---------------------------------------------------------------------------
# 内部工具：在缺少颜色库的情况下推导 hover / 描边
# ---------------------------------------------------------------------------
def _rgb(value: str):
    v = value.lstrip('#')
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)


def _hex(parts):
    return '#' + ''.join(f'{max(0, min(255, round(c))):02X}' for c in parts)


def _hover(value: str, dark: bool, step: int = 12) -> str:
    r, g, b = _rgb(value)
    d = step if dark else -step
    return _hex((r + d, g + d, b + d))


def _line(value: str, dark: bool, step: int = 22) -> str:
    r, g, b = _rgb(value)
    d = step if dark else -step
    return _hex((r + d, g + d, b + d))