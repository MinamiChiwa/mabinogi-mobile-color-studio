import QtQuick
import QtQuick.Window
import QtQuick.Layouts
import QtQuick.Controls

// 选择游戏窗口：圆角 12，列表来自 window_target
Window {
    id: root

    property string selectedHwnd: ''
    property string message: ''

    width: 680
    height: 380
    // 由 window_fx 定位后 show()，避免先出现在系统默认位置再跳
    visible: false
    color: 'transparent'
    flags: Qt.Window | Qt.FramelessWindowHint
    title: Loc.t('选择游戏窗口')

    Component.onCompleted: {
        windowBridge.message.connect(function(text) { root.message = text })
    }

    Rectangle {
        anchors.fill: parent
        radius: 12
        color: uiState.themeColor('bg', uiState.appearance)
        border.width: 1
        border.color: uiState.themeColor('line', uiState.appearance)
        clip: true

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 20
            spacing: 10

            RowLayout {
                Layout.fillWidth: true
                ColumnLayout {
                    spacing: 2
                    Text {
                        text: Loc.t('选择游戏窗口')
                        color: uiState.themeColor('text', uiState.appearance)
                        font.pixelSize: 16
                        font.weight: Font.DemiBold
                    }
                    Text {
                        text: Loc.t('按所选服务器检测游戏窗口；开始时核对客户端版本。')
                        color: uiState.themeColor('muted', uiState.appearance)
                        font.pixelSize: 11
                    }
                }
                Item { Layout.fillWidth: true }
                UiButton { text: '✕'; implicitWidth: 32; onClicked: root.close() }
            }

            Text {
                Layout.fillWidth: true
                text: {
                    void windowBridge.changed
                    return windowBridge.notice()
                }
                color: uiState.themeColor('text_2', uiState.appearance)
                font.pixelSize: 11
                wrapMode: Text.WordWrap
            }

            Flickable {
                Layout.fillWidth: true
                Layout.fillHeight: true
                contentHeight: winList.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: UiScrollBar { }

                ColumnLayout {
                    id: winList
                    width: parent.width
                    spacing: 6

                    Repeater {
                        model: { void windowBridge.changed; return windowBridge.windows() }
                        delegate: Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: 48
                            radius: 8
                            color: root.selectedHwnd === modelData.id
                                   ? uiState.themeColor('accent_soft', uiState.appearance)
                                   : uiState.themeColor('panel', uiState.appearance)
                            border.width: 1
                            border.color: root.selectedHwnd === modelData.id
                                          ? uiState.themeColor('accent', uiState.appearance)
                                          : uiState.themeColor('line', uiState.appearance)

                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: 8
                                spacing: 1
                                Text {
                                    text: modelData.label
                                    color: uiState.themeColor('text', uiState.appearance)
                                    font.pixelSize: 12
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                                Text {
                                    text: modelData.detail
                                    visible: modelData.detail.length > 0
                                    color: uiState.themeColor('faint', uiState.appearance)
                                    font.pixelSize: 10
                                    font.family: 'Consolas'
                                }
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.selectedHwnd = modelData.id
                            }
                        }
                    }
                }
            }

            Text {
                Layout.fillWidth: true
                text: root.message
                visible: root.message.length > 0
                color: uiState.themeColor('danger', uiState.appearance)
                font.pixelSize: 11
                wrapMode: Text.WordWrap
            }

            RowLayout {
                Layout.fillWidth: true
                UiButton { text: Loc.t('刷新窗口'); onClicked: windowBridge.refresh() }
                Item { Layout.fillWidth: true }
                UiButton {
                    text: Loc.t('使用此窗口')
                    kind: 'primary'
                    onClicked: if (root._pick) root._pick(root.selectedHwnd)
                }
            }
        }
    }

    DragHandler {
        target: null
        onActiveChanged: if (active) root.startSystemMove()
    }
}