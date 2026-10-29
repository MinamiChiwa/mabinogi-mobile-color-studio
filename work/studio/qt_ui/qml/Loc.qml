pragma Singleton
import QtQuick

// 界面文案翻译入口（QML 侧）
//
//   text: Loc.t('目标色')
//
// `t()` 内部读取 language，使每个使用它的绑定都依赖语言属性：
// 切换语言时 QML 会自动重算所有文案，不需要逐处 refresh。
QtObject {
    id: loc

    readonly property string language: uiState ? uiState.language : '简体中文'

    function t(source) {
        void language
        if (!uiState) return source
        return uiState.tr(source)
    }
}
