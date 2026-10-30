import QtQuick
import QtQuick.Window
import QtQuick.Layouts
import QtQuick.Controls

// 教程 / 支持等只读信息对话框：圆角 + 可滚动
Window {
    id: root

    width: 680
    height: 640
    // 由 window_fx 定位后 show()，避免先出现在系统默认位置再跳
    visible: false
    color: 'transparent'
    flags: Qt.Window | Qt.FramelessWindowHint
    title: dialogTitle

    Rectangle {
        anchors.fill: parent
        radius: 12
        color: uiState.themeColor('pop', uiState.appearance)
        border.width: 1
        border.color: uiState.themeColor('line', uiState.appearance)
        clip: true

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 20
            spacing: 12

            RowLayout {
                Layout.fillWidth: true
                Text {
                    text: dialogTitle
                    color: uiState.themeColor('text', uiState.appearance)
                    font.pixelSize: 16
                    font.weight: Font.DemiBold
                }
                Item { Layout.fillWidth: true }
                UiButton { text: '✕'; implicitWidth: 32; onClicked: root.close() }
            }

            Flickable {
                Layout.fillWidth: true
                Layout.fillHeight: true
                contentHeight: list.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: UiScrollBar { }

                ColumnLayout {
                    id: list
                    width: parent.width
                    spacing: 10

                    Repeater {
                        model: dialogSections
                        delegate: Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: inner.implicitHeight + 22
                            radius: 8
                            color: uiState.themeColor('panel', uiState.appearance)
                            border.width: 1
                            border.color: uiState.themeColor('line', uiState.appearance)

                            ColumnLayout {
                                id: inner
                                anchors.fill: parent
                                anchors.margins: 11
                                spacing: 4

                                Text {
                                    text: modelData.h
                                    color: uiState.themeColor('accent', uiState.appearance)
                                    font.pixelSize: 12
                                    font.weight: Font.DemiBold
                                    Layout.fillWidth: true
                                    wrapMode: Text.WordWrap
                                }
                                Text {
                                    text: modelData.b
                                    color: uiState.themeColor('text_2', uiState.appearance)
                                    font.pixelSize: 12
                                    Layout.fillWidth: true
                                    wrapMode: Text.WordWrap
                                }
                            }
                        }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Repeater {
                    model: dialogLinks
                    delegate: UiButton {
                        text: modelData.label
                        onClicked: Qt.openUrlExternally(modelData.url)
                    }
                }
                Item { Layout.fillWidth: true }
            }
        }
    }

    // 无边框窗口拖动
    DragHandler {
        target: null
        onActiveChanged: if (active) root.startSystemMove()
    }
}