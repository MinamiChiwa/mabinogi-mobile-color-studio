"""Only unobservable initial color-card/picker layout is retryable."""


class VisualNotReady(ValueError):
    pass


class NativeLayoutNotReady(VisualNotReady):
    def __init__(self,diagnostic):
        super().__init__('已检测到本局色板，但截图中的色卡与取色点尚未完成识别。')
        self.layout_diagnostic=diagnostic


INITIAL_LAYOUT_ERRORS=(
    '未识别到染色小游戏的三张色码卡片。请先进入限时染色界面。',
    '未识别到染色小游戏的完整色码卡片。请先进入限时染色界面。',
    '色码卡片下方点位尚不可见，可能正在显示教学或结果窗口。',
)
