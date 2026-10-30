import QtQuick
import QtQuick.Window
import QtQuick.Layouts
import QtQuick.Controls

// 目标色浮窗 —— ui-spec-v7.md 7.4 / 7.4.1
//   340 宽 · 底色 --pop · 内边距 14 · 圆角 12
//   9×5 色域（列 ±12° 色相 / 行 明度）、最近使用 6、常用色 12、HSL 精调
Window {
    id: root

    property int cardIndex: 0
    property var bridge
    // picker 由 contextProperty(pickerState) 注入，这里起别名
    readonly property var picker: pickerState

    width: 340
    // 高度按内容（设计稿：内容自适应，超高时内部滚动）
    height: Math.min(720, body.implicitHeight + pad * 2)
    visible: false
    color: 'transparent'
    flags: Qt.Popup | Qt.FramelessWindowHint
    title: Loc.t('选择目标色')

    readonly property int pad: 14

    function sliderRow(key, label, min, max, value, suffix, c0, c1, c2) {
        return { key: key, label: label, min: min, max: max, value: value,
                 suffix: suffix, c0: c0, c1: c1, c2: c2 }
    }

    function rowColor(row, stop) {
        if (row.key === 'hue') return stop === 0 ? '#FF0000' : (stop === 1 ? '#00FF00' : '#FF0000')
        if (row.key === 'sat') return stop === 0 ? row.c0 : row.c1
        return stop === 0 ? '#000000' : (stop === 1 ? row.c1 : '#FFFFFF')
    }

    Rectangle {
        id: shell
        anchors.fill: parent
        radius: uiState.themeRadius('dialog', uiState.appearance)
        color: uiState.themeColor('pop', uiState.appearance)
        border.width: 1
        border.color: uiState.themeColor('pop_line', uiState.appearance)
        clip: true

        // 阴影用一层外描边近似（QML 无 CSS box-shadow）
        Rectangle {
            anchors.fill: parent
            anchors.margins: -1
            radius: shell.radius + 1
            color: 'transparent'
            border.width: 1
            border.color: '#33FFFFFF'
            z: -1
        }

        ColumnLayout {
            id: body
            anchors.fill: parent
            anchors.margins: root.pad
            spacing: 10

            // ---------- 标题行 ----------
            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                Text {
                    text: Loc.t(picker.title)
                    color: uiState.themeColor('text', uiState.appearance)
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                }

                Item { Layout.fillWidth: true }

                Text {
                    text: picker.target
                    color: uiState.themeColor('muted_2', uiState.appearance)
                    font.pixelSize: 11
                    font.family: 'Consolas'
                }

                Text {
                    text: '✕'
                    color: uiState.themeColor('muted', uiState.appearance)
                    font.pixelSize: 13
                    MouseArea {
                        anchors.fill: parent
                        anchors.margins: -4
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.close()
                    }
                }
            }

            // ---------- 9×5 色域（列 ±12° 色相 / 行 明度） ----------
            Grid {
                Layout.fillWidth: true
                columns: 9
                columnSpacing: 3
                rowSpacing: 3

                Repeater {
                    model: picker.grid.length === 5 ? 45 : 0
                    delegate: Rectangle {
                        readonly property int rowIndex: Math.floor(index / 9)
                        readonly property int colIndex: index % 9
                        width: Math.floor((shell.width - 28 - 8 * 3) / 9)
                        height: width
                        radius: 4
                        color: picker.grid[rowIndex][colIndex]
                        border.width: (rowIndex === 2 && colIndex === 4) ? 2 : 1
                        border.color: (rowIndex === 2 && colIndex === 4)
                                      ? uiState.themeColor('text', uiState.appearance)
                                      : '#1AFFFFFF'

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                picker.pick_cell(rowIndex, colIndex)
                                bridge.setTarget(cardIndex, picker.target)
                            }
                        }
                    }
                }
            }

            // ---------- 最近使用 ----------
            Column {
                Layout.fillWidth: true
                spacing: 5
                visible: picker.recent.length > 0

                Text {
                    text: Loc.t('最近使用')
                    color: uiState.themeColor('muted', uiState.appearance)
                    font.pixelSize: 10
                }

                Row {
                    spacing: 5
                    Repeater {
                        model: picker.recent
                        delegate: Rectangle {
                            width: 20
                            height: 20
                            radius: 4
                            color: modelData
                            border.width: 1
                            border.color: '#24FFFFFF'
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    picker.pick_color(modelData)
                                    bridge.setTarget(cardIndex, picker.target)
                                }
                            }
                        }
                    }
                }
            }

            // ---------- 常用色 ----------
            Column {
                Layout.fillWidth: true
                spacing: 5

                Text {
                    text: Loc.t('常用色')
                    color: uiState.themeColor('muted', uiState.appearance)
                    font.pixelSize: 10
                }

                Grid {
                    columns: 12
                    spacing: 4
                    Repeater {
                        model: picker.common
                        delegate: Rectangle {
                            width: (body.width - 11 * 4) / 12
                            height: width
                            radius: 4
                            color: modelData
                            border.width: 1
                            border.color: '#24FFFFFF'
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    picker.pick_color(modelData)
                                    bridge.setTarget(cardIndex, picker.target)
                                }
                            }
                        }
                    }
                }
            }

            // ---------- 精调（HSL） ----------
            Rectangle {
                Layout.fillWidth: true
                height: 1
                color: uiState.themeColor('line_soft', uiState.appearance)
            }

            RowLayout {
                Layout.fillWidth: true
                Text {
                    text: Loc.t('精调')
                    color: uiState.themeColor('muted_2', uiState.appearance)
                    font.pixelSize: 11
                }
                Item { Layout.fillWidth: true }
                Text {
                    text: 'HSL'
                    color: uiState.themeColor('faint', uiState.appearance)
                    font.pixelSize: 9
                    font.family: 'Consolas'
                }
            }

            // 三行：标签 34 + 滑杆 + 数值 38
            // 所有派生值在顶层算好，delegate 只读 modelData（深层作用域拿不到外部 id）
            Repeater {
                model: [
                    sliderRow('hue', Loc.t('色调'), 0, 360, picker.hue, '°',
                              '#FF0000', '#00FF00', '#FF0000'),
                    sliderRow('sat', Loc.t('饱和度'), 0, 100, picker.sat, '%',
                              picker.satTrack[0], picker.satTrack[1], picker.satTrack[1]),
                    sliderRow('lig', Loc.t('亮度'), 0, 100, picker.lig, '%',
                              '#000000', picker.ligTrack[1], '#FFFFFF')
                ]

                delegate: RowLayout {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 23
                    spacing: 8

                    Text {
                        Layout.preferredWidth: 34
                        text: modelData.label
                        // 中性色时色调标签降级（ui-spec 7.4.1）
                        color: (modelData.key === 'hue' && picker.neutral)
                               ? '#5C626F' : '#6F7480'
                        font.pixelSize: 10
                    }

                    // 渐变轨道 + 滑块
                    Item {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 14

                        readonly property real ratio: {
                            var v = modelData.value
                            return Math.max(0, Math.min(1,
                                (v - modelData.min) / Math.max(1, modelData.max - modelData.min)))
                        }

                        Rectangle {
                            anchors.verticalCenter: parent.verticalCenter
                            width: parent.width
                            height: 6
                            radius: 3

                            // 轨道渐变（三档，取自顶层算好的颜色）
                            Rectangle {
                                anchors.fill: parent
                                radius: parent.radius
                                gradient: Gradient {
                                    orientation: Gradient.Horizontal
                                    GradientStop { position: 0.0; color: modelData.c0 }
                                    GradientStop { position: 0.5; color: modelData.c1 }
                                    GradientStop { position: 1.0; color: modelData.c2 }
                                }
                            }

                            // 滑块 12px 白点 + 1px 黑描边
                            Rectangle {
                                width: 12
                                height: 12
                                radius: 6
                                x: Math.max(0, Math.min(parent.width - width,
                                                        parent.width * parent.parent.ratio - width / 2))
                                anchors.verticalCenter: parent.verticalCenter
                                color: '#FFFFFF'
                                border.width: 1
                                border.color: '#000000'
                                opacity: (modelData.key === 'hue' && picker.neutral) ? 0.45 : 1.0
                            }
                        }

                        MouseArea {
                            anchors.fill: parent
                            anchors.topMargin: -4
                            anchors.bottomMargin: -4
                            cursorShape: (modelData.key === 'hue' && picker.neutral)
                                         ? Qt.ArrowCursor : Qt.PointingHandCursor
                            enabled: picker.available && !(modelData.key === 'hue' && picker.neutral)

                            function apply(x) {
                                var w = width
                                var r = Math.max(0, Math.min(1, x / w))
                                var v = Math.round(modelData.min + r * (modelData.max - modelData.min))
                                if (modelData.key === 'hue')
                                    picker.adjust(v, picker.sat, picker.lig)
                                else if (modelData.key === 'sat')
                                    picker.adjust(picker.hue, v, picker.lig)
                                else
                                    picker.adjust(picker.hue, picker.sat, v)
                                bridge.setTarget(cardIndex, picker.target)
                            }

                            onPressed: function(m) { apply(m.x) }
                            onPositionChanged: function(m) { if (pressed) apply(m.x) }
                            onWheel: function(w) { w.accepted = false }
                        }
                    }

                    Text {
                        Layout.preferredWidth: 38
                        horizontalAlignment: Text.AlignRight
                        text: modelData.value + modelData.suffix
                        color: uiState.themeColor('text', uiState.appearance)
                        font.pixelSize: 10
                        font.family: 'Consolas'
                    }
                }
            }

            Text {
                Layout.fillWidth: true
                text: Loc.t('拖动即时写入目标色；松开后色板以新颜色为中心')
                color: uiState.themeColor('faint', uiState.appearance)
                font.pixelSize: 9
                wrapMode: Text.WordWrap
            }

            Text {
                Layout.fillWidth: true
                text: Loc.t('点击色块替换目标色 · 方向键移动')
                color: uiState.themeColor('faint', uiState.appearance)
                font.pixelSize: 9
            }
        }
    }
}