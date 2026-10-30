import QtQuick
import QtQuick.Window
import QtQuick.Layouts
import QtQuick.Controls

// 寻色记录：圆角 + 可滚动，数据来自 result_history 的既有结构
Window {
    id: root

    width: 820
    height: 620
    // 由 window_fx 定位后 show()，避免先出现在系统默认位置再跳
    visible: false
    color: 'transparent'
    flags: Qt.Window | Qt.FramelessWindowHint
    title: Loc.t('寻色记录')

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
                        text: Loc.t('寻色记录')
                        color: uiState.themeColor('text', uiState.appearance)
                        font.pixelSize: 16
                        font.weight: Font.DemiBold
                    }
                    Text {
                        text: Loc.t('记录最近 50 次结果 · ΔE 越小越接近目标，0 表示目标原色')
                        color: uiState.themeColor('muted', uiState.appearance)
                        font.pixelSize: 11
                    }
                }
                Item { Layout.fillWidth: true }
                UiButton { text: '✕'; implicitWidth: 32; onClicked: root.close() }
            }

            Text {
                visible: historyRows.length === 0
                text: Loc.t('完成一次寻色后，颜色组合会自动保存在这里。')
                color: uiState.themeColor('muted', uiState.appearance)
                font.pixelSize: 12
                Layout.alignment: Qt.AlignHCenter
                Layout.topMargin: 40
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
                    spacing: 8

                    Repeater {
                        model: historyRows
                        delegate: Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: body.implicitHeight + 20
                            radius: 10
                            color: uiState.themeColor('panel', uiState.appearance)
                            border.width: 1
                            border.color: uiState.themeColor('line', uiState.appearance)

                            ColumnLayout {
                                id: body
                                anchors.fill: parent
                                anchors.margins: 10
                                spacing: 8

                                Text {
                                    Layout.fillWidth: true
                                    text: {
                                        var names = { matched: Loc.t('目标达标'), compromise: Loc.t('妥协结果'),
                                                      applied: Loc.t('已套用'), observed: Loc.t('当前色码记录') }
                                        var t = modelData.time + '  ·  '
                                                + (names[modelData.outcome] || Loc.t('寻色结果'))
                                        if (modelData.maximum !== null && modelData.maximum !== undefined)
                                            t += Loc.t(' · 最大 ΔE ') + modelData.maximum.toFixed(2)
                                               + Loc.t(' / 平均 ') + modelData.average.toFixed(2)
                                        return t
                                    }
                                    color: uiState.themeColor('text', uiState.appearance)
                                    font.pixelSize: 12
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 6

                                    Repeater {
                                        model: modelData.regions
                                        delegate: Rectangle {
                                            Layout.fillWidth: true
                                            implicitHeight: 46
                                            radius: 8
                                            color: modelData.color || '#28364A'

                                            Text {
                                                anchors.centerIn: parent
                                                text: {
                                                    var t = Loc.t('区域') + ' ' + modelData.region + '  '
                                                          + (modelData.color || Loc.t('未识别'))
                                                    t += (modelData.delta !== null && modelData.delta !== undefined)
                                                         ? '\nΔE ' + modelData.delta.toFixed(2)
                                                         : '\n' + Loc.t('未参与匹配')
                                                    return t
                                                }
                                                color: uiState.themeColor('text', uiState.appearance)
                                                font.pixelSize: 10
                                                horizontalAlignment: Text.AlignHCenter
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    DragHandler {
        target: null
        onActiveChanged: if (active) root.startSystemMove()
    }
}
