import QtQuick
import QtQuick.Window
import QtQuick.Layouts
import QtQuick.Controls

// 软件更新 —— ui-spec-v7.md 7.8 / 7.9
//   宽 560 · 圆角 12 · 正文可滚动 · 状态与按钮可用性全部来自 updatePanel.view
//   业务动作（check / download / install / cancel / ignore / later）转发给 UpdateRuntime
Window {
    id: root

    readonly property var d: updatePanel.view

    width: 560
    height: Math.min(760, Math.max(420, body.implicitHeight + 56))
    minimumWidth: 420
    minimumHeight: 360
    // 由 window_fx 定位后 show()，避免先出现在系统默认位置再跳
    visible: false
    color: 'transparent'
    flags: Qt.Window | Qt.FramelessWindowHint
    title: root.d.title

    Rectangle {
        anchors.fill: parent
        radius: 12
        color: uiState.themeColor('pop', uiState.appearance)
        border.width: 1
        border.color: uiState.themeColor('line', uiState.appearance)
        clip: true

        ColumnLayout {
            id: body
            anchors.fill: parent
            anchors.margins: 20
            spacing: 12

            // ---- 标题栏 ----
            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                Text {
                    text: root.d.title
                    color: uiState.themeColor('text', uiState.appearance)
                    font.pixelSize: 16
                    font.weight: Font.DemiBold
                }
                Item { Layout.fillWidth: true }
                UiButton {
                    text: '✕'
                    implicitWidth: 32
                    onClicked: root.close()
                }
            }

            // ---- 状态区 ----
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 6

                Text {
                    Layout.fillWidth: true
                    text: root.d.heading
                    color: uiState.themeColor('text', uiState.appearance)
                    font.pixelSize: 15
                    font.weight: Font.DemiBold
                    wrapMode: Text.WordWrap
                }

                Text {
                    Layout.fillWidth: true
                    text: root.d.body
                    color: uiState.themeColor('text_2', uiState.appearance)
                    font.pixelSize: 12
                    lineHeight: 1.6
                    wrapMode: Text.WordWrap
                }

                // 进度：下载 / 安装时出现
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: 2
                    spacing: 4
                    visible: root.d.progressVisible

                    Rectangle {
                        Layout.fillWidth: true
                        height: 3
                        radius: 2
                        color: uiState.themeColor('track', uiState.appearance)

                        Rectangle {
                            width: Math.max(0, Math.min(1, root.d.progressValue)) * parent.width
                            height: parent.height
                            radius: 2
                            color: uiState.themeColor('green', uiState.appearance)
                            Behavior on width {
                                NumberAnimation { duration: 180 }
                            }
                        }
                    }
                }

                // 忙碌提示：寻色 / 取色 / 选窗进行中
                Text {
                    Layout.fillWidth: true
                    visible: root.d.busyNotice.length > 0
                    text: root.d.busyNotice
                    color: uiState.themeColor('amber', uiState.appearance)
                    font.pixelSize: 10
                    wrapMode: Text.WordWrap
                }
            }

            // ---- 两个复选框 ----
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 6

                UiCheck {
                    Layout.fillWidth: true
                    label: root.d.autoLabel
                    checked: root.d.automatic
                    onToggled: function(value) { updatePanel.setAutomatic(value) }
                }

                UiCheck {
                    Layout.fillWidth: true
                    label: root.d.preLabel
                    checked: root.d.prerelease
                    onToggled: function(value) { updatePanel.setPrerelease(value) }
                }
            }

            Item { Layout.fillHeight: true }

            // ---- 操作区 ----
            GridLayout {
                Layout.fillWidth: true
                columns: 2
                columnSpacing: 8
                rowSpacing: 8

                Repeater {
                    model: root.d.actions
                    delegate: UiButton {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 34
                        text: modelData.label
                        kind: (modelData.primary && modelData.enabled) ? 'primary'
                              : modelData.key === 'later' ? 'ghost' : 'secondary'
                        enabled: modelData.enabled
                        onClicked: updatePanel.act(modelData.key)
                    }
                }
            }

            // ---- 脚注 ----
            Text {
                Layout.fillWidth: true
                text: root.d.notice
                color: uiState.themeColor('faint', uiState.appearance)
                font.pixelSize: 10
                lineHeight: 1.5
                wrapMode: Text.WordWrap
            }
        }
    }

    DragHandler {
        target: null
        onActiveChanged: if (active) root.startSystemMove()
    }
}
