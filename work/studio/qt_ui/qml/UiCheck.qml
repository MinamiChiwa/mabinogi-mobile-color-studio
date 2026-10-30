import QtQuick
import QtQuick.Layouts

// 复选框 —— ui-spec-v7.md 7.9 的两个开关（自动检查 / 允许候选版本）
//   16×16 圆角 4；选中时绿底描边 + ✓；整行可点
RowLayout {
    id: line

    property string label: ''
    property bool checked: false
    signal toggled(bool value)

    spacing: 8

    Rectangle {
        width: 16
        height: 16
        radius: 4
        color: line.checked ? uiState.themeColor('green_soft', uiState.appearance) : 'transparent'
        border.width: 1
        border.color: line.checked ? uiState.themeColor('green', uiState.appearance)
                                   : uiState.themeColor('field_line', uiState.appearance)

        Text {
            anchors.centerIn: parent
            visible: line.checked
            text: '✓'
            color: uiState.themeColor('green', uiState.appearance)
            font.pixelSize: 10
        }

        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: line.toggled(!line.checked)
        }
    }

    Text {
        Layout.fillWidth: true
        text: line.label
        color: uiState.themeColor('muted_2', uiState.appearance)
        font.pixelSize: 12

        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: line.toggled(!line.checked)
        }
    }
}
