import QtQuick

// 环境条里的「游戏窗口」按钮（原型 .window-button）
//   高 32 · 圆角 6 · 最大宽 380 · 状态点 + 省略文本 + ▾
Rectangle {
    id: root

    signal clicked()

    implicitHeight: 32
    radius: uiState.themeRadius('control', uiState.appearance)
    color: hover.hovered ? uiState.themeColor('btn_hover', uiState.appearance)
                         : uiState.themeColor('field', uiState.appearance)
    border.width: 1
    border.color: hover.hovered ? '#41454F'
                                : uiState.themeColor('field_line', uiState.appearance)
    Behavior on border.color { ColorAnimation { duration: 150 } }
    Behavior on color { ColorAnimation { duration: 150 } }

    // 按下反馈：与 UiButton/UiCombo 一致，避免点下去毫无反馈
    scale: windowArea.pressed ? 0.985 : 1.0
    Behavior on scale { NumberAnimation { duration: 110; easing.type: Easing.OutCubic } }

    Row {
        anchors.fill: parent
        anchors.leftMargin: 10
        anchors.rightMargin: 10
        spacing: 8

        Rectangle {
            width: 6
            height: 6
            radius: 3
            anchors.verticalCenter: parent.verticalCenter
            color: uiState.windowBound
                   ? uiState.themeColor('green', uiState.appearance)
                   : uiState.themeColor('faint', uiState.appearance)
            Behavior on color { ColorAnimation { duration: 180 } }
        }

        Text {
            width: Math.max(0, parent.width - 34)
            anchors.verticalCenter: parent.verticalCenter
            // 组合文案在 QML 里拼，语言切换才能整句跟着换
            text: uiState.windowBound
                  ? Loc.t('游戏窗口 · ') + uiState.windowTitle
                  : Loc.t('自动检测') + ' · ' + (uiState.windowTitle || Loc.t('未检测到唯一窗口'))
            color: uiState.themeColor('muted_2', uiState.appearance)
            font.pixelSize: 11
            elide: Text.ElideRight
        }

        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: '▾'
            color: uiState.themeColor('faint', uiState.appearance)
            font.pixelSize: 9
        }
    }

    HoverHandler { id: hover }

    MouseArea {
        id: windowArea
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }
}
