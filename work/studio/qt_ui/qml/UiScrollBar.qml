import QtQuick
import QtQuick.Controls

// 滚动条 —— 深色主题下的细条，避免系统默认的白条压在 V7 面板上
//   轨道透明、滑块 6px 圆角 3、拖拽时提亮；不占用内容宽度（覆盖式）
ScrollBar {
    id: bar

    policy: ScrollBar.AsNeeded
    width: 8
    padding: 1
    minimumSize: 0.08

    contentItem: Rectangle {
        implicitWidth: 6
        implicitHeight: 6
        radius: 3
        color: bar.pressed ? uiState.themeColor('muted_2', uiState.appearance)
                           : uiState.themeColor('muted', uiState.appearance)
        opacity: bar.active ? 0.85 : 0.45
        visible: bar.size < 1.0

        Behavior on color {
            ColorAnimation { duration: 120 }
        }
    }

    background: Item {}
}
