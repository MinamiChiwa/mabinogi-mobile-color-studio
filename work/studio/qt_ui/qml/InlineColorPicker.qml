import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// 就地展开的目标色面板 —— 嵌在目标色行下方，不弹独立窗口。
//
// 视觉取自 ui-spec-v7.md 7.4：9×5 色域（列 ±12° 色相 / 行明度）、
// 中央格高亮、最近使用、常用色、HSL 精调。
// 承载方式改为内联，因此尺寸按卡片宽度自适应，不再固定 340。
Rectangle {
    id: picker

    property int cardIndex: 0
    property var card: ({})
    property var bridge
    // true = 自带边框底色（独立使用）；false = 作为浮层内容，去掉自身外框
    property bool framed: true

    readonly property int animBase: uiState.motion('base')
    readonly property int animMid: uiState.motion('mid')
    readonly property int gridSize: 9
    readonly property real cellGap: 3

    // 由卡片宽度决定每格边长（减去两侧留白与间隙）
    readonly property real cellSide: Math.max(14,
        Math.floor((width - (gridSize - 1) * cellGap) / gridSize))

    // 面板高度上限：超过就在面板内滚动，避免撑破卡片（自动布局不能被内容牵着走）
    readonly property int maxHeight: 368
    implicitHeight: Math.min(content.implicitHeight, maxHeight)
    radius: framed ? uiState.themeRadius('control', uiState.appearance) : 0
    color: framed ? uiState.themeColor('field', uiState.appearance) : 'transparent'
    border.width: framed ? 1 : 0
    border.color: uiState.themeColor('field_line', uiState.appearance)
    clip: true

    Flickable {
        id: scroll
        anchors.fill: parent
        contentWidth: width
        contentHeight: content.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: UiScrollBar { }

    ColumnLayout {
        id: content
        width: scroll.width
        spacing: 8

        // ---------- 标题行 ----------
        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Text {
                text: Loc.t('选择目标色')
                color: uiState.themeColor('text', uiState.appearance)
                font.pixelSize: 11
                font.weight: Font.Medium
            }

            Item { Layout.fillWidth: true }

            Text {
                text: card.target || ''
                color: uiState.themeColor('muted_2', uiState.appearance)
                font.pixelSize: 10
                font.family: 'Consolas'
            }

            // 收起
            Item {
                width: 18
                height: 18
                Text {
                    anchors.centerIn: parent
                    text: '✕'
                    color: uiState.themeColor('muted', uiState.appearance)
                    font.pixelSize: 11
                }
                MouseArea {
                    anchors.fill: parent
                    anchors.margins: -4
                    cursorShape: Qt.PointingHandCursor
                    onClicked: bridge.closePicker()
                }
            }
        }

        // ---------- 9×5 色域 ----------
        Grid {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignHCenter
            columns: picker.gridSize
            columnSpacing: picker.cellGap
            rowSpacing: picker.cellGap

            Repeater {
                model: (card.pickerGrid && card.pickerGrid.length === 5) ? 45 : 0
                delegate: Rectangle {
                    readonly property int rowIndex: Math.floor(index / 9)
                    readonly property int colIndex: index % 9
                    readonly property bool isCenter: rowIndex === 2 && colIndex === 4

                    width: picker.cellSide
                    height: picker.cellSide
                    radius: 3
                    color: card.pickerGrid[rowIndex][colIndex]
                    border.width: isCenter ? 2 : 1
                    border.color: isCenter ? uiState.themeColor('text', uiState.appearance) : '#1AFFFFFF'

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: bridge.pickerCell(cardIndex, rowIndex, colIndex)
                    }
                }
            }
        }

        // ---------- 最近使用 ----------
        RowLayout {
            Layout.fillWidth: true
            spacing: 5
            visible: (card.pickerRecent || []).length > 0

            Text {
                text: Loc.t('最近')
                color: uiState.themeColor('muted', uiState.appearance)
                font.pixelSize: 9
            }

            Repeater {
                model: card.pickerRecent || []
                delegate: Rectangle {
                    width: 16
                    height: 16
                    radius: 3
                    color: modelData
                    border.width: 1
                    border.color: '#24FFFFFF'
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: bridge.pickerColor(cardIndex, modelData)
                    }
                }
            }

            Item { Layout.fillWidth: true }
        }

        // ---------- 常用色 ----------
        Grid {
            Layout.fillWidth: true
            columns: 12
            columnSpacing: 3
            rowSpacing: 3

            Repeater {
                model: card.pickerCommon || []
                delegate: Rectangle {
                    width: Math.max(10, Math.floor((picker.width - 11 * 3) / 12))
                    height: width
                    radius: 3
                    color: modelData
                    border.width: 1
                    border.color: '#24FFFFFF'
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: bridge.pickerColor(cardIndex, modelData)
                    }
                }
            }
        }

        // ---------- 分隔 ----------
        Rectangle {
            Layout.fillWidth: true
            height: 1
            color: uiState.themeColor('line_soft', uiState.appearance)
        }

        // ---------- HSL 精调 ----------
        RowLayout {
            Layout.fillWidth: true
            Text {
                text: Loc.t('精调')
                color: uiState.themeColor('muted_2', uiState.appearance)
                font.pixelSize: 10
            }
            Item { Layout.fillWidth: true }
            Text {
                text: 'HSL'
                color: uiState.themeColor('faint', uiState.appearance)
                font.pixelSize: 9
                font.family: 'Consolas'
            }
        }

        Repeater {
            // 只用**静态** key 列表做 model。
            // 之前 model 是内联 JS 数组、里面的 value/c0/c1 直接引用 card.pickerXxx，
            // 每次拖一次滑块 → 状态更新 → 数组被重建 → Repeater 销毁并重建全部
            // 委托，鼠标抢占随之丢失，于是「只能单击、拖不动」。
            // 现在动态值都放在委托内部做绑定，委托对象保持稳定。
            model: ['hue', 'sat', 'lig']

            delegate: RowLayout {
                id: sliderRow
                Layout.fillWidth: true
                Layout.preferredHeight: 18
                spacing: 6

                // ---- 由 key 推导出的动态属性（绑定会随 card 更新，委托不重建）----
                readonly property string key: modelData
                readonly property int sliderMin: key === 'hue' ? 0 : 0
                readonly property int sliderMax: key === 'hue' ? 360 : 100
                readonly property int sliderValue:
                    key === 'hue' ? (card.pickerHue || 0)
                  : key === 'sat' ? (card.pickerSat || 0)
                                  : (card.pickerLig || 0)
                readonly property string sliderSuffix: key === 'hue' ? '°' : '%'
                readonly property string sliderLabel:
                    key === 'hue' ? Loc.t('色调')
                  : key === 'sat' ? Loc.t('饱和')
                                  : Loc.t('亮度')
                readonly property string trackC0:
                    key === 'hue' ? '#FF0000'
                  : key === 'sat' ? ((card.pickerSatTrack || [])[0] || '#000000')
                                  : '#000000'
                readonly property string trackC1:
                    key === 'hue' ? '#00FF00'
                  : key === 'sat' ? ((card.pickerSatTrack || [])[1] || '#FFFFFF')
                                  : ((card.pickerLigTrack || [])[1] || '#808080')
                readonly property string trackC2:
                    key === 'hue' ? '#FF0000'
                  : key === 'sat' ? ((card.pickerSatTrack || [])[1] || '#FFFFFF')
                                  : '#FFFFFF'

                Text {
                    Layout.preferredWidth: 26
                    text: sliderRow.sliderLabel
                    color: uiState.themeColor('muted', uiState.appearance)
                    font.pixelSize: 9
                }

                Item {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 12

                    readonly property real ratio: Math.max(0, Math.min(1,
                        (sliderRow.sliderValue - sliderRow.sliderMin)
                        / Math.max(1, sliderRow.sliderMax - sliderRow.sliderMin)))

                    Rectangle {
                        anchors.verticalCenter: parent.verticalCenter
                        width: parent.width
                        height: 5
                        radius: 2.5

                        Rectangle {
                            anchors.fill: parent
                            radius: parent.radius
                            gradient: Gradient {
                                orientation: Gradient.Horizontal
                                GradientStop { position: 0.0; color: sliderRow.trackC0 }
                                GradientStop { position: 0.5; color: sliderRow.trackC1 }
                                GradientStop { position: 1.0; color: sliderRow.trackC2 }
                            }
                        }

                        // 滑块 10px 白点
                        Rectangle {
                            width: 10
                            height: 10
                            radius: 5
                            x: Math.max(0, Math.min(parent.width - width,
                                                    parent.width * parent.parent.ratio - width / 2))
                            anchors.verticalCenter: parent.verticalCenter
                            color: '#FFFFFF'
                            border.width: 1
                            border.color: '#000000'
                        }
                    }

                    MouseArea {
                        objectName: 'pickerSlider_' + sliderRow.key
                        anchors.fill: parent
                        anchors.topMargin: -3
                        anchors.bottomMargin: -3
                        cursorShape: Qt.PointingHandCursor
                        // 三条滑杆始终可拖：中性色（黑/白/灰）下饱和度回填为 0，
                        // 之前用 pickerNeutral 把色调滑杆置灰禁用，导致点过标准色后
                        // 「色调拖不动」；这里不再按颜色状态禁用任何一条。
                        enabled: true

                        function apply(x) {
                            var r = Math.max(0, Math.min(1, x / width))
                            var v = Math.round(sliderRow.sliderMin
                                               + r * (sliderRow.sliderMax - sliderRow.sliderMin))
                            if (sliderRow.key === 'hue')
                                bridge.pickerSlide(cardIndex, v, card.pickerSat, card.pickerLig)
                            else if (sliderRow.key === 'sat')
                                bridge.pickerSlide(cardIndex, card.pickerHue, v, card.pickerLig)
                            else
                                bridge.pickerSlide(cardIndex, card.pickerHue, card.pickerSat, v)
                        }

                        onPressed: function(m) { apply(m.x) }
                        onPositionChanged: function(m) { if (pressed) apply(m.x) }
                        onWheel: function(w) { w.accepted = false }
                    }
                }

                Text {
                    Layout.preferredWidth: 30
                    horizontalAlignment: Text.AlignRight
                    text: sliderRow.sliderValue + sliderRow.sliderSuffix
                    color: uiState.themeColor('text', uiState.appearance)
                    font.pixelSize: 9
                    font.family: 'Consolas'
                }
            }
        }
    }
    }
}