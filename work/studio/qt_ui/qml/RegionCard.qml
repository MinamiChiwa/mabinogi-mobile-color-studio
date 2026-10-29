import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// 区域卡 —— V2（紧凑版）
//
//   V7 的节奏保留，纵向整体压缩：
//     padding 12/14/12 · head 34 · 目标色行 12+32 · 模式行 10+1+12+26
//     容差行 8+16 · 替代色 10+20 · 目标色集合 12+1+12+14+5+缩略图
//     读数 10+1+15+5+15
//
//   交互（V2）：目标色块与目标色集合都在**浮层**里打开，
//   浮层按锚点位置自动向上/向下/向侧边弹出，不再撑高卡片。
Rectangle {
    id: cardRoot

    objectName: 'card' + cardIndex

    property int cardIndex: 0
    property var uiBridge

    readonly property var card: {
        void uiState.revision
        return uiState.cardAt(cardIndex)
    }

    readonly property int animMid: uiState.motion('mid')
    readonly property int animBase: uiState.motion('base')
    readonly property bool tight: width < 300

    radius: uiState.themeRadius('card', uiState.appearance)
    color: card.pickerOpen
           ? uiState.themeColor('card_open', uiState.appearance)
           : (card.cardBg || uiState.themeColor('panel', uiState.appearance))
    border.width: card.cardBorder || 1
    border.color: card.pickerOpen
                  ? uiState.themeColor('card_open_line', uiState.appearance)
                  : (card.cardLine || uiState.themeColor('line', uiState.appearance))

    opacity: !card.available ? 0.45 : (card.enabled ? 1.0 : 0.6)
    Behavior on opacity { NumberAnimation { duration: animMid } }
    Behavior on color { ColorAnimation { duration: animMid } }
    Behavior on border.color { ColorAnimation { duration: animMid } }

    readonly property color cText: uiState.themeColor('text', uiState.appearance)
    readonly property color cMuted: uiState.themeColor('muted', uiState.appearance)
    readonly property color cFaint: uiState.themeColor('faint', uiState.appearance)
    readonly property color cMuted2: uiState.themeColor('muted_2', uiState.appearance)
    readonly property color cSoftLine: uiState.themeColor('line_soft', uiState.appearance)

    // 统一的文字样式
    readonly property int labelSize: 12

    // 行首标签列宽：中文 3 字足够 52，英文（Alternatives / Tolerance）更长。
    // 由字体度量算出，保证翻译后不裁字、滑块宽度同步收缩。
    TextMetrics {
        id: labelMetrics
        text: Loc.t('替代色')
        font.pixelSize: 12
        font.family: 'Microsoft YaHei UI'
    }
    readonly property int labelW: Math.max(52, Math.ceil(labelMetrics.advanceWidth) + 6)

    // 分段控件的两段宽度（用字体度量，避免 children 顺序依赖）
    TextMetrics {
        id: segMetrics0
        text: Loc.t('精准 HEX')
        font.pixelSize: 12
        font.family: 'Microsoft YaHei UI'
    }
    TextMetrics {
        id: segMetrics1
        text: Loc.t('相似颜色')
        font.pixelSize: 12
        font.family: 'Microsoft YaHei UI'
    }
    readonly property real segW0: segMetrics0.advanceWidth + 20
    readonly property real segW1: segMetrics1.advanceWidth + 20

    ColumnLayout {
        anchors.fill: parent
        anchors.topMargin: 12
        anchors.bottomMargin: 12
        anchors.leftMargin: 14
        anchors.rightMargin: 14
        spacing: 0

        // =================================================================
        // 身份 / 开关（高 34）
        // =================================================================
        Item {
            Layout.fillWidth: true
            implicitHeight: 34

            Row {
                id: idRow
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                spacing: 8

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    // 标题由「区域 + 序号」组合，序号不参与翻译
                    text: Loc.t('区域') + ' ' + (cardIndex + 1)
                    color: cardRoot.cText
                    font.pixelSize: 14
                    font.weight: Font.DemiBold
                    font.letterSpacing: 0.5
                }

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: Loc.t(card.enableText || '')
                    color: card.enabled ? cardRoot.cMuted : cardRoot.cFaint
                    font.pixelSize: 12
                    Behavior on color { ColorAnimation { duration: animBase } }
                }

                // 开关 32×18
                Item {
                    id: toggle
                    width: 32
                    height: 18
                    anchors.verticalCenter: parent.verticalCenter

                    Rectangle {
                        anchors.fill: parent
                        radius: 9
                        color: card.enabled ? uiState.themeColor('green', uiState.appearance)
                                            : '#3A3D45'
                        Behavior on color { ColorAnimation { duration: animMid } }
                    }

                    Rectangle {
                        width: 14
                        height: 14
                        radius: 7
                        y: 2
                        x: card.enabled ? parent.width - width - 2 : 2
                        color: '#FFFFFF'
                        Behavior on x { NumberAnimation { duration: animMid; easing.type: Easing.OutCubic } }
                    }

                    MouseArea {
                        objectName: 'enableSwitch' + cardIndex
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        enabled: card.available
                        onClicked: uiBridge.toggleEnabled(cardIndex)
                    }
                }
            }

            Row {
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                spacing: 6

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    visible: !cardRoot.tight
                    text: Loc.t('优先级')
                    color: cardRoot.cMuted
                    font.pixelSize: 12
                }

                UiCombo {
                    width: 52
                    implicitHeight: 28
                    model: ['1', '2', '3']
                    current: String(card.priority || 1)
                    enabled: card.available
                    onActivated: function(v) { uiBridge.setPriority(cardIndex, parseInt(v)) }
                }
            }
        }

        // =================================================================
        // 目标色（mt12 h32）
        // =================================================================
        Item {
            Layout.fillWidth: true
            implicitHeight: 32 + 12

            Row {
                anchors.fill: parent
                anchors.topMargin: 12
                spacing: 8

                Text {
                    width: cardRoot.labelW
                    anchors.verticalCenter: parent.verticalCenter
                    text: Loc.t('目标色')
                    color: cardRoot.cMuted
                    font.pixelSize: cardRoot.labelSize
                }

                // 色块 32×32：点击弹出锚定色板
                Rectangle {
                    id: swatch
                    width: 32
                    height: 32
                    radius: 7
                    anchors.verticalCenter: parent.verticalCenter
                    color: card.swatchColor || '#000000'
                    border.width: 1
                    border.color: swatchHover.hovered
                                  ? uiState.themeColor('muted', uiState.appearance)
                                  : uiState.themeColor('field_line', uiState.appearance)
                    scale: swatchArea.pressed ? 0.96 : (swatchHover.hovered ? 1.03 : 1.0)
                    Behavior on scale { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
                    Behavior on border.color { ColorAnimation { duration: animBase } }

                    Rectangle {
                        anchors.fill: parent
                        anchors.margins: 1
                        radius: 6
                        color: 'transparent'
                        border.width: 1
                        border.color: '#59000000'
                    }

                    // hover 提示三角
                    Canvas {
                        width: 5
                        height: 5
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        anchors.rightMargin: 3
                        anchors.bottomMargin: 3
                        opacity: swatchHover.hovered ? 1 : 0
                        Behavior on opacity { NumberAnimation { duration: 140 } }
                        onPaint: {
                            var ctx = getContext('2d')
                            ctx.reset()
                            ctx.fillStyle = 'rgba(255,255,255,0.45)'
                            ctx.beginPath()
                            ctx.moveTo(width, height)
                            ctx.lineTo(0, height)
                            ctx.lineTo(width, 0)
                            ctx.closePath()
                            ctx.fill()
                        }
                    }

                    HoverHandler { id: swatchHover }

                    MouseArea {
                        id: swatchArea
                        objectName: 'swatchArea' + cardIndex
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        enabled: card.available
                        onClicked: {
                            if (card.pickerOpen) uiBridge.closePicker()
                            else uiBridge.openPicker(cardIndex)
                        }
                    }
                }

                UiField {
                    width: parent.width - 52 - 32 - 30 - 32
                    fieldHeight: 32
                    anchors.verticalCenter: parent.verticalCenter
                    text: card.target || ''
                    placeholder: '#RRGGBB'
                    enabled: card.available
                    invalid: !card.targetValid
                    onEdited: function(v) { uiBridge.setTarget(cardIndex, v) }
                }

                // 吸管 30×32
                Rectangle {
                    width: 30
                    height: 32
                    radius: uiState.themeRadius('control', uiState.appearance)
                    anchors.verticalCenter: parent.verticalCenter
                    color: eyeHover.hovered && card.available ? uiState.themeColor('btn', uiState.appearance)
                                                              : 'transparent'
                    border.width: 1
                    border.color: eyeHover.hovered && card.available
                                  ? '#3C4049'
                                  : uiState.themeColor('field_line', uiState.appearance)
                    Behavior on color { ColorAnimation { duration: animBase } }

                    Canvas {
                        width: 13
                        height: 13
                        anchors.centerIn: parent
                        property color stroke: eyeHover.hovered && card.available
                                                ? cardRoot.cText : cardRoot.cMuted
                        onStrokeChanged: requestPaint()
                        onPaint: {
                            var ctx = getContext('2d')
                            var k = width / 24
                            ctx.reset()
                            ctx.scale(k, k)
                            ctx.strokeStyle = stroke
                            ctx.lineWidth = 1.7
                            ctx.lineCap = 'round'
                            ctx.lineJoin = 'round'
                            ctx.beginPath()
                            ctx.moveTo(14.5, 4.5); ctx.lineTo(19.5, 9.5)
                            ctx.moveTo(13, 6); ctx.lineTo(18, 11)
                            ctx.moveTo(4, 20); ctx.lineTo(5.2, 15.8); ctx.lineTo(15.6, 5.4)
                            ctx.quadraticCurveTo(16.6, 4.2, 18.4, 6.2)
                            ctx.lineTo(8.2, 18.8)
                            ctx.closePath()
                            ctx.stroke()
                        }
                    }

                    HoverHandler { id: eyeHover }

                    MouseArea {
                        objectName: 'eyedropperBtn' + cardIndex
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        enabled: card.available
                        onClicked: uiBridge.eyedropper(cardIndex)
                    }
                }
            }
        }

        // =================================================================
        // 颜色要求（mt10 + 分隔线 + pt12，内容 26）
        //   分段控件带滑动指示块；ΔE 徽标随模式淡入淡出
        // =================================================================
        Item {
            Layout.fillWidth: true
            implicitHeight: 10 + 1 + 12 + 26

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                y: 10
                height: 1
                color: cardRoot.cSoftLine
            }

            Item {
                anchors.left: parent.left
                anchors.top: parent.top
                anchors.topMargin: 10 + 1 + 12
                height: 26
                width: segBox.width

                Item {
                    id: segBox
                    width: cardRoot.segW0 + cardRoot.segW1 + 4
                    height: 26

                    Rectangle {
                        anchors.fill: parent
                        radius: uiState.themeRadius('control', uiState.appearance)
                        // 浅色主题下 field 与卡片同为白色，用 track_off 做出「凹槽」对比
                        color: uiState.themeColor('track_off', uiState.appearance)
                        border.width: 1
                        border.color: uiState.themeColor('line', uiState.appearance)
                    }

                    // 滑动指示块
                    Rectangle {
                        id: segPill
                        y: 2
                        height: 22
                        radius: 4
                        color: uiState.themeColor('btn', uiState.appearance)
                        border.width: 1
                        border.color: uiState.themeColor('btn_line', uiState.appearance)
                        x: card.exact ? 2 : 2 + cardRoot.segW0
                        width: card.exact ? cardRoot.segW0 : cardRoot.segW1
                        Behavior on x { NumberAnimation { duration: 190; easing.type: Easing.OutCubic } }
                        Behavior on width { NumberAnimation { duration: 190; easing.type: Easing.OutCubic } }
                        Behavior on color { ColorAnimation { duration: animBase } }
                    }

                    Row {
                        id: segRow
                        anchors.fill: parent
                        anchors.margins: 2
                        spacing: 0

                        Repeater {
                            model: ['精准 HEX', '相似颜色']
                            delegate: Item {
                                width: index === 0 ? cardRoot.segW0 : cardRoot.segW1
                                height: parent.height

                                Text {
                                    id: segText
                                    anchors.centerIn: parent
                                    text: Loc.t(modelData)
                                    font.pixelSize: 12
                                    color: (card.exact === (index === 0)) ? cardRoot.cText : cardRoot.cMuted
                                    Behavior on color { ColorAnimation { duration: animBase } }
                                }

                                MouseArea {
                                    objectName: 'modeSeg' + cardIndex + '_' + index
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    enabled: card.available
                                    // 按下反馈：任何点击都有回应（包括重复点当前项）
                                    onPressed: parent.scale = 0.96
                                    onReleased: parent.scale = 1.0
                                    onCanceled: parent.scale = 1.0
                                    onClicked: uiBridge.setMode(cardIndex, index === 0)
                                }
                                Behavior on scale { NumberAnimation { duration: 110 } }
                            }
                        }
                    }
                }
            }

            // ΔE 徽标
            Rectangle {
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.topMargin: 10 + 1 + 12
                width: 50
                height: 22
                radius: 5
                color: uiState.themeColor('panel_alt', uiState.appearance)
                border.width: 1
                border.color: uiState.themeColor('line', uiState.appearance)

                opacity: card.exact ? 0 : 1
                scale: card.exact ? 0.9 : 1
                visible: opacity > 0.02
                Behavior on opacity { NumberAnimation { duration: animMid } }
                Behavior on scale { NumberAnimation { duration: animMid; easing.type: Easing.OutCubic } }

                Text {
                    anchors.centerIn: parent
                    text: 'ΔE ' + Math.round(card.tolerance || 8)
                    font.family: 'Consolas'
                    font.pixelSize: 11
                    color: cardRoot.cText
                }
            }
        }

        // =================================================================
        // 容差（mt8 h16，精准模式折叠）
        // =================================================================
        Item {
            id: tolRow
            objectName: 'tolRow' + cardIndex
            Layout.fillWidth: true
            implicitHeight: card.exact ? 0 : 24
            clip: true
            Behavior on implicitHeight { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }

            Row {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.topMargin: 8
                height: 16
                spacing: 8
                visible: !card.exact

                Text {
                    width: cardRoot.labelW
                    anchors.verticalCenter: parent.verticalCenter
                    text: Loc.t('容差')
                    color: cardRoot.cMuted
                    font.pixelSize: cardRoot.labelSize
                }

                UiSlider {
                    objectName: 'tolSlider' + cardIndex
                    width: parent.width - cardRoot.labelW - 8
                    implicitHeight: 16
                    from: 1
                    to: 35
                    value: card.tolerance || 8
                    enabled: card.available
                    onMoved: function(v) { uiBridge.setTolerance(cardIndex, v) }
                }
            }
        }

        // =================================================================
        // 替代色（mt10 h20）
        // =================================================================
        Item {
            id: altBlock
            Layout.fillWidth: true
            Layout.topMargin: 10
            implicitHeight: 20 + (altEditor.visible ? 6 + 28 : 0)
            Behavior on implicitHeight { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }

            Row {
                id: altRow
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: parent.right
                height: 20
                spacing: 5

                Text {
                    width: cardRoot.labelW
                    anchors.verticalCenter: parent.verticalCenter
                    text: Loc.t('替代色')
                    color: cardRoot.cMuted
                    font.pixelSize: cardRoot.labelSize
                }

                Row {
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 5

                    Repeater {
                        model: (card.alts || []).slice(0, 6)
                        delegate: Rectangle {
                            width: 20
                            height: 20
                            radius: 4
                            color: modelData
                            border.width: 1
                            border.color: '#24FFFFFF'
                            scale: chipHover.hovered ? 1.12 : 1.0
                            Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }

                            HoverHandler { id: chipHover }

                            // 点击删除：hover 时右上角出现 ×
                            Rectangle {
                                width: 11
                                height: 11
                                radius: 5.5
                                x: 13
                                y: -4
                                color: '#2B2E37'
                                border.width: 1
                                border.color: '#3A3E48'
                                visible: chipHover.hovered && card.available
                                opacity: visible ? 1 : 0
                                Behavior on opacity { NumberAnimation { duration: 100 } }

                                Text {
                                    anchors.centerIn: parent
                                    text: '×'
                                    font.pixelSize: 8
                                    color: '#C8CDD5'
                                }
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                enabled: card.available
                                onClicked: uiBridge.removeAlt(cardIndex, modelData)
                            }
                        }
                    }

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        visible: (card.alts || []).length > 6
                        text: '+' + Math.max(0, (card.alts || []).length - 6)
                        color: cardRoot.cFaint
                        font.pixelSize: 10
                    }

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        visible: (card.alts || []).length === 0
                        text: Loc.t('无')
                        color: cardRoot.cFaint
                        font.pixelSize: 10
                    }

                    Rectangle {
                        width: 20
                        height: 20
                        radius: 4
                        color: plusHover.hovered ? uiState.themeColor('btn', uiState.appearance) : 'transparent'
                        border.width: 1
                        border.color: plusHover.hovered ? '#5A6470' : '#3C464F'
                        opacity: card.available ? 1.0 : 0.4
                        Behavior on color { ColorAnimation { duration: animBase } }

                        Text {
                            anchors.centerIn: parent
                            text: '+'
                            font.pixelSize: 12
                            color: plusHover.hovered ? cardRoot.cText : cardRoot.cMuted
                        }

                        HoverHandler { id: plusHover }

                        MouseArea {
                            objectName: 'altAdd' + cardIndex
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            enabled: card.available
                            onClicked: {
                                altEditor.visible = !altEditor.visible
                                if (altEditor.visible) {
                                    altInput.text = ''
                                    altInput.forceActiveFocus()
                                }
                            }
                        }
                    }
                }
            }

            Row {
                id: altEditor
                visible: false
                anchors.top: altRow.bottom
                anchors.topMargin: 6
                anchors.left: parent.left
                anchors.right: parent.right
                spacing: 5
                height: 28

                UiField {
                    id: altInput
                    width: parent.width - 104
                    fieldHeight: 28
                    text: ''
                    placeholder: '#FFFFFF'
                    onEdited: invalid = false
                }

                Rectangle {
                    width: 46
                    height: 28
                    radius: uiState.themeRadius('control', uiState.appearance)
                    color: plusBtnHover.hovered ? uiState.themeColor('btn_hover', uiState.appearance)
                                                : uiState.themeColor('btn', uiState.appearance)
                    border.width: 1
                    border.color: uiState.themeColor('btn_line', uiState.appearance)

                    Text {
                        anchors.centerIn: parent
                        text: Loc.t('添加')
                        font.pixelSize: 11
                        color: cardRoot.cText
                    }
                    HoverHandler { id: plusBtnHover }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            var v = altInput.text.trim()
                            if (v.length === 0) return
                            // 校验沿用原模块的 normalize_hex（经 bridge 转发）
                            if (!uiBridge.validHex(v)) {
                                altInput.invalid = true
                                return
                            }
                            altInput.invalid = false
                            var cur = (card.alt || '').trim()
                            uiBridge.setAlt(cardIndex, cur.length ? cur + ', ' + v : v)
                            altEditor.visible = false
                        }
                    }
                }

                Rectangle {
                    width: 46
                    height: 28
                    radius: uiState.themeRadius('control', uiState.appearance)
                    color: 'transparent'
                    border.width: 1
                    border.color: uiState.themeColor('line', uiState.appearance)

                    Text {
                        anchors.centerIn: parent
                        text: Loc.t('取消')
                        font.pixelSize: 11
                        color: cardRoot.cMuted2
                    }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: altEditor.visible = false
                    }
                }
            }
        }

        // =================================================================
        // 目标色集合（mt12 + 分隔线 + pt12；缩略图 688:265）
        //   点击缩略图 → 锚定浮层（含缩放），浮层里可再开完整窗口
        // =================================================================
        Item {
            id: atlasBlock
            Layout.fillWidth: true
            Layout.topMargin: 12
            Layout.fillHeight: true
            implicitHeight: 1 + 12 + 14 + 5 + Math.round(width * 265 / 688)

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                height: 1
                color: cardRoot.cSoftLine
            }

            Item {
                id: atlasHead
                anchors.top: parent.top
                anchors.topMargin: 1 + 12
                anchors.left: parent.left
                anchors.right: parent.right
                height: 14

                Text {
                    anchors.left: parent.left
                    anchors.baseline: parent.bottom
                    anchors.baselineOffset: -1
                    text: Loc.t('目标色集合')
                    color: cardRoot.cMuted
                    font.pixelSize: cardRoot.labelSize
                }

                Text {
                    anchors.right: parent.right
                    anchors.baseline: parent.bottom
                    anchors.baselineOffset: -1
                    text: card.paletteCount
                          ? Loc.t(card.paletteCount === 1 ? '%1 色（单） · 点击查看全部'
                                                          : '%1 色 · 点击查看全部')
                                 .replace('%1', Number(card.paletteCount).toLocaleString())
                          : ''
                    color: cardRoot.cFaint
                    font.pixelSize: 10
                    font.family: 'Consolas'
                    elide: Text.ElideLeft
                    width: Math.min(implicitWidth, atlasHead.width - 76)
                }
            }

            Rectangle {
                id: atlasThumb
                objectName: 'atlasThumb' + cardIndex
                anchors.top: atlasHead.bottom
                anchors.topMargin: 5
                anchors.left: parent.left
                anchors.right: parent.right
                // 高度吃掉卡片剩余空间；最小保持 688:265 的比例
                height: Math.max(Math.round(width * 265 / 688),
                                 atlasBlock.height - (1 + 12 + 14 + 5))
                // 圆角取 12：6px 在大面积色块上几乎看不出来（原型也是圆角矩形）
                readonly property int corner: 12
                radius: corner
                color: uiState.themeColor('track_off', uiState.appearance)
                // 描边改由上层单独画：图片要铺到最外沿（含四角），
                // 容器自带的 border 会被图片盖住，只在未加载时露出来。
                border.width: 0
                clip: true

                // 颜色铺满整个色块（含四角），圆角由 Canvas 裁出来
                RoundedImage {
                    objectName: 'atlasCanvas' + cardIndex
                    anchors.fill: parent
                    radius: atlasThumb.corner
                    source: card.paletteImage || ''
                    visible: !!card.paletteImage
                }

                // 1px 描边画在图片之上，hover 时提亮
                Rectangle {
                    anchors.fill: parent
                    radius: atlasThumb.corner
                    color: 'transparent'
                    border.width: 1
                    border.color: atlasHover.hovered ? '#48FFFFFF' : '#1FFFFFFF'
                    Behavior on border.color { ColorAnimation { duration: animBase } }
                }

                Text {
                    anchors.centerIn: parent
                    visible: !card.paletteImage
                    text: Loc.t('色板计算中…')
                    color: cardRoot.cFaint
                    font.pixelSize: 10
                }

                // 右上角放大提示
                Rectangle {
                    width: 16
                    height: 16
                    x: parent.width - width - 4
                    y: 4
                    radius: 4
                    color: '#73000000'
                    border.width: 1
                    border.color: '#2EFFFFFF'
                    opacity: atlasHover.hovered ? 1.0 : 0.55
                    Behavior on opacity { NumberAnimation { duration: 140 } }

                    Text {
                        anchors.centerIn: parent
                        text: '⤢'
                        color: '#FFFFFF'
                        font.pixelSize: 9
                    }
                }

                HoverHandler { id: atlasHover }

                // 按下反馈：大面积色块上给一点内缩，点击才有「接住了」的手感
                scale: atlasArea.pressed ? 0.992 : 1.0
                Behavior on scale { NumberAnimation { duration: 130; easing.type: Easing.OutCubic } }

                MouseArea {
                    id: atlasArea
                    anchors.fill: parent
                    cursorShape: card.paletteImage ? Qt.ZoomInCursor : Qt.ArrowCursor
                    enabled: !!card.paletteImage
                    onClicked: {
                        if (card.atlasOpen) uiBridge.closeAtlas()
                        else uiBridge.openAtlas(cardIndex)
                    }
                }
            }
        }

        // =================================================================
        // 读数（pt10 + 分隔线，两行 15 间距 5）
        // =================================================================
        Item {
            id: readsBlock
            Layout.fillWidth: true
            implicitHeight: 10 + 1 + 15 + 5 + 15

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                y: 10
                height: 1
                color: cardRoot.cSoftLine
            }

            Row {
                id: curRow
                anchors.left: parent.left
                anchors.top: parent.top
                anchors.topMargin: 10 + 1
                height: 15
                spacing: 6

                Rectangle {
                    width: 11
                    height: 11
                    radius: 3
                    anchors.verticalCenter: parent.verticalCenter
                    color: card.currentDot && card.currentDot.length ? card.currentDot : 'transparent'
                    border.width: 1
                    border.color: card.currentDot && card.currentDot.length ? '#24FFFFFF' : 'transparent'
                    Behavior on color { ColorAnimation { duration: 160 } }
                }

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: Loc.t('当前')
                    color: cardRoot.cMuted
                    font.pixelSize: 11
                }

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: (card.currentHex && card.currentHex.length) ? card.currentHex : '—'
                    color: cardRoot.cMuted2
                    font.pixelSize: 11
                    font.family: 'Consolas'
                    font.letterSpacing: 0.3
                }
            }

            Row {
                id: meaRow
                anchors.left: parent.left
                anchors.top: curRow.bottom
                anchors.topMargin: 5
                height: 15
                spacing: 6

                Rectangle {
                    width: 11
                    height: 11
                    radius: 3
                    anchors.verticalCenter: parent.verticalCenter
                    color: card.bestDot && card.bestDot.length ? card.bestDot : 'transparent'
                    border.width: 1
                    border.color: card.bestDot && card.bestDot.length ? '#24FFFFFF' : 'transparent'
                    Behavior on color { ColorAnimation { duration: 160 } }
                }

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: Loc.t('实测')
                    color: cardRoot.cMuted
                    font.pixelSize: 11
                }

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: (card.bestHex && card.bestHex.length) ? card.bestHex : '—'
                    color: cardRoot.cMuted2
                    font.pixelSize: 11
                    font.family: 'Consolas'
                    font.letterSpacing: 0.3
                }
            }

            Row {
                anchors.right: parent.right
                anchors.top: meaRow.top
                height: 15
                spacing: 6

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: card.deText || 'ΔE —'
                    color: cardRoot.cFaint
                    font.pixelSize: 10
                    font.family: 'Consolas'
                    visible: (card.deText || '').length > 0
                }

                Rectangle {
                    id: badge
                    anchors.verticalCenter: parent.verticalCenter
                    width: Math.max(40, badgeText.implicitWidth + 10)
                    height: 15
                    radius: 4
                    color: card.badgeTone === 'good'
                           ? uiState.themeColor('green_soft', uiState.appearance)
                           : card.badgeTone === 'warn'
                             ? uiState.themeColor('selected', uiState.appearance)
                             : 'transparent'
                    border.width: 1
                    border.color: card.badgeTone === 'good'
                                  ? uiState.themeColor('green', uiState.appearance)
                                  : card.badgeTone === 'warn'
                                    ? uiState.themeColor('amber', uiState.appearance)
                                    : uiState.themeColor('line', uiState.appearance)
                    Behavior on color { ColorAnimation { duration: 160 } }

                    Text {
                        id: badgeText
                        anchors.centerIn: parent
                        text: card.badge ? Loc.t(card.badge) : Loc.t('未开始')
                        font.pixelSize: 9
                        color: card.badgeTone === 'good'
                               ? uiState.themeColor('accent', uiState.appearance)
                               : card.badgeTone === 'warn'
                                 ? uiState.themeColor('amber', uiState.appearance)
                                 : cardRoot.cMuted
                    }
                }
            }
        }
    }

    // 状态驱动浮层显隐：任何入口打开色板（含脚本、快捷键）都能弹出
    onCardChanged: {
        if (card.pickerOpen && !colorPop.open) colorPop.show()
        else if (!card.pickerOpen && colorPop.open) colorPop.close()
        if (card.atlasOpen && !atlasPop.open) atlasPop.show()
        else if (!card.atlasOpen && atlasPop.open) atlasPop.close()
    }

    // =====================================================================
    // 浮层：目标色面板
    //   挂在窗口 contentItem 上，不参与卡片布局；位置由 Popover 计算
    // =====================================================================
    Popover {
        id: colorPop
        objectName: 'colorPop' + cardIndex
        parent: cardRoot.Window.window ? cardRoot.Window.window.contentItem : null
        anchorItem: swatch
        contentWidth: 336
        contentHeight: Math.min(pickerPanel.implicitHeight + 24, 392)

        onOpenChanged: {
            if (!open && cardRoot.card.pickerOpen) uiBridge.closePicker()
            uiState.reportPopover(cardRoot.cardIndex, 'color', open, placement,
                                  _targetX, _targetY, contentWidth, contentHeight)
        }
        onPlacementChanged: if (open) uiState.reportPopover(cardRoot.cardIndex, 'color', true,
                                                            placement, _targetX, _targetY,
                                                            contentWidth, contentHeight)
        onContentHeightChanged: if (open) uiState.reportPopover(cardRoot.cardIndex, 'color', true,
                                                                placement, _targetX, _targetY,
                                                                contentWidth, contentHeight)

        InlineColorPicker {
            id: pickerPanel
            anchors.fill: parent
            framed: false
            cardIndex: cardRoot.cardIndex
            card: cardRoot.card
            bridge: cardRoot.uiBridge
        }
    }

    // =====================================================================
    // 浮层：目标色集合
    // =====================================================================
    Popover {
        id: atlasPop
        objectName: 'atlasPop' + cardIndex
        parent: cardRoot.Window.window ? cardRoot.Window.window.contentItem : null
        anchorItem: atlasThumb
        contentWidth: Math.min(500, cardRoot.Window.window ? cardRoot.Window.window.width - 40 : 500)
        contentHeight: 336
        onOpenChanged: {
            if (!open && cardRoot.card.atlasOpen) uiBridge.closeAtlas()
            uiState.reportPopover(cardRoot.cardIndex, 'atlas', open, placement,
                                  _targetX, _targetY, contentWidth, contentHeight)
        }
        onPlacementChanged: if (open) uiState.reportPopover(cardRoot.cardIndex, 'atlas', true,
                                                            placement, _targetX, _targetY,
                                                            contentWidth, contentHeight)

        AtlasPanel {
            anchors.fill: parent
            card: cardRoot.card
            bridge: cardRoot.uiBridge
            cardIndex: cardRoot.cardIndex
        }
    }
}
