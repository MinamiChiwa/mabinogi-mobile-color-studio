import QtQuick
import QtQuick.Controls

// 下拉 —— ui-spec-v7.md 7.3 / 原型 .select
//   高 32 · 最小宽 56 · 圆角 6 · 描边 #36373C
//   hover 描边 #4A4C53 + 底 #1E2027；focus 描边 --green + 2px 环
Item {
    id: combo

    property var model: []
    property string current: ''
    property bool enabled: true
    property bool compact: false        // true 时用于卡片优先级（高 32 但更窄）
    // 显示时翻译；值本身始终是 model 里的原文（回调拿到的也是原文），
    // 所以切语言不会破坏 current / activated 的比较。
    property bool translate: true

    signal activated(string value)

    implicitHeight: 32
    implicitWidth: 56
    readonly property int animBase: uiState.motion('base')

    Rectangle {
        id: face
        anchors.fill: parent
        radius: uiState.themeRadius('control', uiState.appearance)
        scale: comboArea.pressed ? 0.985 : 1.0
        Behavior on scale { NumberAnimation { duration: 110; easing.type: Easing.OutCubic } }
        color: hover.hovered && combo.enabled ? '#1E2027' : 'transparent'
        border.width: 1
        border.color: !combo.enabled ? '#2C2E34'
                      : (hover.hovered ? '#4A4C53' : '#36373C')
        Behavior on border.color { ColorAnimation { duration: combo.animBase } }
        Behavior on color { ColorAnimation { duration: combo.animBase } }

        Text {
            anchors.left: parent.left
            anchors.leftMargin: 10
            anchors.right: caret.left
            anchors.rightMargin: 6
            anchors.verticalCenter: parent.verticalCenter
            text: combo.translate ? Loc.t(combo.current) : combo.current
            color: combo.enabled ? uiState.themeColor('text', uiState.appearance) : uiState.themeColor('muted', uiState.appearance)
            font.pixelSize: 12
            elide: Text.ElideRight
        }

        Text {
            id: caret
            anchors.right: parent.right
            anchors.rightMargin: 8
            anchors.verticalCenter: parent.verticalCenter
            text: '▾'
            color: uiState.themeColor('muted', uiState.appearance)
            font.pixelSize: 9
        }

        HoverHandler { id: hover }
    }

    MouseArea {
        id: comboArea
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        enabled: combo.enabled
        onClicked: popup.visible ? popup.close() : popup.open()
    }

    Popup {
        id: popup
        y: combo.height + 4
        width: Math.max(combo.width, 120)
        padding: 4
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        enter: Transition {
            ParallelAnimation {
                NumberAnimation { property: 'opacity'; from: 0; to: 1; duration: 120 }
                NumberAnimation { property: 'scale'; from: 0.97; to: 1; duration: 150; easing.type: Easing.OutCubic }
            }
        }
        exit: Transition {
            NumberAnimation { property: 'opacity'; from: 1; to: 0; duration: 90 }
        }

        background: Rectangle {
            radius: 8
            color: uiState.themeColor('pop', uiState.appearance)
            border.width: 1
            border.color: uiState.themeColor('pop_line', uiState.appearance)
        }

        contentItem: ListView {
            implicitHeight: Math.min(contentHeight, 260)
            clip: true
            model: combo.model
            boundsBehavior: Flickable.StopAtBounds

            delegate: Item {
                width: ListView.view.width
                height: 30

                Rectangle {
                    anchors.fill: parent
                    radius: 5
                    color: rowHover.hovered ? '#2D313B' : 'transparent'
                }

                Text {
                    anchors.left: parent.left
                    anchors.leftMargin: 9
                    anchors.right: parent.right
                    anchors.rightMargin: 9
                    anchors.verticalCenter: parent.verticalCenter
                    text: combo.translate ? Loc.t(modelData) : modelData
                    color: modelData === combo.current
                           ? uiState.themeColor('text', uiState.appearance)
                           : uiState.themeColor('muted_2', uiState.appearance)
                    font.pixelSize: 12
                    elide: Text.ElideRight
                }

                HoverHandler { id: rowHover }

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        popup.close()
                        if (modelData !== combo.current) combo.activated(modelData)
                    }
                }
            }
        }
    }
}