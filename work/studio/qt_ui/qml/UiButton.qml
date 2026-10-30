import QtQuick
import QtQuick.Controls

// 普通按钮 —— ui-spec-v7.md 4.3 / 7.1
//   底色 #262933 · 描边 #343841 · 文字 --muted-2
//   hover #2D313B / #41454F / --text
//   圆角 6、高 32（主按钮 primary：高 38、圆角 7、绿底 #10200F 字）
Item {
    id: button

    property string text: ''
    property string kind: 'secondary'      // primary | secondary | ghost | stop
    property bool selected: false
    property bool compact: false           // 高 26，用于浮窗内小按钮

    signal clicked()

    readonly property int animBase: uiState.motion('base')

    implicitWidth: Math.max(labelText.implicitWidth + 26, compact ? 44 : 0)
    implicitHeight: compact ? 26 : 32
    opacity: enabled ? 1.0 : 0.45

    readonly property color faceColor: {
        if (kind === 'primary') return uiState.themeColor('green', uiState.appearance)
        if (kind === 'stop') return uiState.themeColor('green_soft', uiState.appearance)
        if (kind === 'ghost') return 'transparent'
        return uiState.themeColor('btn', uiState.appearance)
    }

    readonly property color faceHover: {
        if (kind === 'primary') return '#70CF77'
        if (kind === 'stop') return '#3A5D43'
        return uiState.themeColor('btn_hover', uiState.appearance)
    }

    // 按下反馈：主按钮下沉 1px，所有按钮轻微缩放（统一动效）
    property bool down: false
    y: down && kind === 'primary' ? 1 : 0
    scale: down ? 0.975 : (hover.hovered && enabled ? 1.012 : 1.0)
    Behavior on y { NumberAnimation { duration: 70 } }
    Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }

    Rectangle {
        id: face
        anchors.fill: parent
        radius: button.kind === 'primary' ? 7 : 6
        color: hover.hovered && button.enabled ? button.faceHover : button.faceColor
        border.width: button.kind === 'ghost' ? 1 : 1
        border.color: {
            if (button.kind === 'primary') return uiState.themeColor('green', uiState.appearance)
            if (button.kind === 'ghost') return uiState.themeColor('line', uiState.appearance)
            if (button.kind === 'stop') return uiState.themeColor('green_soft', uiState.appearance)
            return hover.hovered && button.enabled ? '#41454F' : uiState.themeColor('btn_line', uiState.appearance)
        }

        Behavior on color { ColorAnimation { duration: button.animBase } }
        Behavior on border.color { ColorAnimation { duration: button.animBase } }

        Text {
            id: labelText
            anchors.centerIn: parent
            text: button.text
            font.pixelSize: button.kind === 'primary' ? 13 : 12
            font.weight: button.kind === 'primary' ? Font.DemiBold : Font.Medium
            color: {
                if (button.kind === 'primary') return '#10200F'
                if (button.kind === 'stop') return uiState.themeColor('text', uiState.appearance)
                return (hover.hovered && button.enabled)
                       ? uiState.themeColor('text', uiState.appearance)
                       : uiState.themeColor('muted_2', uiState.appearance)
            }
            Behavior on color { ColorAnimation { duration: button.animBase } }
        }

        HoverHandler { id: hover }
    }

    MouseArea {
        id: press
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        enabled: button.enabled
        onPressed: button.down = true
        onReleased: button.down = false
        onCanceled: button.down = false
        onExited: button.down = false
        onClicked: button.clicked()
    }

    focus: true
}