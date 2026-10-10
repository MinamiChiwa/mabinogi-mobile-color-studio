"""Only unobservable initial color-card/picker layout is retryable."""


class VisualNotReady(ValueError):
    pass


INITIAL_LAYOUT_ERRORS=(
    '未识别到染色小游戏的三张色码卡片。请先进入限时染色界面。',
    '未识别到染色小游戏的完整色码卡片。请先进入限时染色界面。',
    '色码卡片下方点位尚不可见，可能正在显示教学或结果窗口。',
)
