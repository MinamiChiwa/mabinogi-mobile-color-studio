import QtQuick
import QtQuick.Window
import QtQuick.Layouts
import QtQuick.Controls

// 寻色浮窗 —— ui-spec-v7.md 7.7
//   宽 min(410, 100vw-16) · 圆角 10 · --panel/--line
//   标题 15/600 --green + 6px 状态点（运行 1.8s 呼吸）
//   计时 剩余 mm:ss（等宽 13，≤10s 变琥珀）· 进度 3px
//   候选卡 --pop/--pop-line、8px 内边距、圆角 8
//   折叠后 46 高，仅留标题栏与 mini 停止
//   不做整窗透明度；截图排除/不抢焦点由 Python 侧对 HWND 注册
Window {
    id: root

    width: Math.min(410, Screen.width - 16)
    // 高度按内容自适应（设计稿实测：等待 224 / 拼接 203 / 候选 587 / 复核 397 / 收起 46）
    height: overlayState.collapsed ? 46 : Math.max(180, content.implicitHeight + 24)
    minimumWidth: 320
    visible: false
    color: 'transparent'
    flags: Qt.Window | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus | Qt.WindowStaysOnTopHint
    title: Loc.t('寻色浮窗')

    Behavior on height { NumberAnimation { duration: uiState.motion('mid') } }

    // 状态点呼吸（1.8s，原型 @keyframes breathe）
    SequentialAnimation on dotHalo {
        running: overlayState.running && !overlayState.collapsed
        loops: Animation.Infinite
        NumberAnimation { to: 5; duration: 900; easing.type: Easing.InOutQuad }
        NumberAnimation { to: 3; duration: 900; easing.type: Easing.InOutQuad }
    }
    property real dotHalo: 3

    Rectangle {
        anchors.fill: parent
        radius: uiState.themeRadius('card', uiState.appearance)
        color: uiState.themeColor('panel', uiState.appearance)
        border.width: 1
        border.color: uiState.themeColor('line', uiState.appearance)
        clip: true

        ColumnLayout {
            id: content
            anchors.fill: parent
            anchors.margins: 12
            spacing: 0

            // ================= 标题栏（拖动把手） =================
            Item {
                id: titleBar
                Layout.fillWidth: true
                implicitHeight: 22

                Row {
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 8

                    // 6px 状态点 + 呼吸光晕
                    Item {
                        width: 16
                        height: 16
                        anchors.verticalCenter: parent.verticalCenter

                        Rectangle {
                            anchors.centerIn: parent
                            width: 6 + root.dotHalo * 2
                            height: width
                            radius: width / 2
                            color: overlayState.running ? '#145DC264' : 'transparent'
                        }
                        Rectangle {
                            width: 6
                            height: 6
                            radius: 3
                            anchors.centerIn: parent
                            color: overlayState.running
                                   ? uiState.themeColor('green', uiState.appearance)
                                   : (overlayState.warn ? uiState.themeColor('amber', uiState.appearance)
                                                        : uiState.themeColor('faint', uiState.appearance))
                        }
                    }

                    Text {
                        text: overlayState.title
                        color: uiState.themeColor('green', uiState.appearance)
                        font.pixelSize: 15
                        font.weight: Font.DemiBold
                        elide: Text.ElideRight
                        width: Math.max(80, root.width - 210)
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }

                Row {
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 6

                    // 计时：剩余 mm:ss
                    Row {
                        spacing: 4
                        anchors.verticalCenter: parent.verticalCenter
                        visible: overlayState.remaining.length > 0

                        Text {
                            text: Loc.t('剩余')
                            color: uiState.themeColor('faint', uiState.appearance)
                            font.pixelSize: 10
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Text {
                            text: overlayState.remaining
                            color: overlayState.lowTime ? uiState.themeColor('amber', uiState.appearance)
                                                        : uiState.themeColor('text', uiState.appearance)
                            font.pixelSize: 13
                            font.family: 'Consolas'
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }

                    // 设置（不透明度）：设计稿 .ov-ico#gear
                    Item {
                        id: gearButton
                        width: 22
                        height: 22
                        anchors.verticalCenter: parent.verticalCenter

                        Text {
                            anchors.centerIn: parent
                            text: '⚙'
                            font.pixelSize: 11
                            color: gearHover.hovered || opacityPanel.visible
                                   ? uiState.themeColor('muted_2', uiState.appearance)
                                   : uiState.themeColor('faint', uiState.appearance)
                        }
                        HoverHandler { id: gearHover }
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: opacityPanel.visible = !opacityPanel.visible
                        }
                    }

                    // 折叠 / 展开
                    Item {
                        width: 22
                        height: 22
                        Text {
                            anchors.centerIn: parent
                            text: overlayState.collapsed ? '▾' : '▴'
                            color: uiState.themeColor('faint', uiState.appearance)
                            font.pixelSize: 10
                        }
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: overlayBridge.toggleCollapse()
                        }
                    }
                }

                // 拖动：仅标题栏
                DragHandler {
                    target: null
                    acceptedDevices: PointerDevice.Mouse
                    onActiveChanged: if (active) root.startSystemMove()
                }
            }

            // ================= 正文（折叠时隐藏） =================
            ColumnLayout {
                Layout.fillWidth: true
                Layout.topMargin: 8
                visible: !overlayState.collapsed
                spacing: 0

                // 阶段行（设计稿 .ov-stage）：左阶段名 + 右步骤/数量
                Item {
                    Layout.fillWidth: true
                    Layout.topMargin: 6
                    implicitHeight: 16
                    // progress_text 生成的标题已含阶段名与步骤（「采集颜色板  3/8」），
                    // 此时阶段行是重复信息；只有标题没覆盖时才显示。
                    visible: overlayState.stage.length > 0
                             && overlayState.title.indexOf(overlayState.stage) < 0

                    Text {
                        anchors.left: parent.left
                        anchors.verticalCenter: parent.verticalCenter
                        text: overlayState.stage
                        color: uiState.themeColor('muted_2', uiState.appearance)
                        font.pixelSize: 11
                        elide: Text.ElideRight
                        width: Math.min(implicitWidth, parent.width - 90)
                    }

                    Text {
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        visible: overlayState.stageMeta.length > 0
                        text: overlayState.stageMeta
                        color: uiState.themeColor('faint', uiState.appearance)
                        font.pixelSize: 10
                        font.family: 'Consolas'
                    }
                }

                // 进度条 3px
                //
                // 两条独立通路，避免「确定性模式静止不动」：
                //   · 不确定（progress < 0）→ 38% 宽的滑块来回扫
                //   · 确定（progress >= 0） → 填充宽度平滑过渡 + 常在流光
                // 流光不受 progress 数值影响，所以即使长时间停在同一进度
                // （例如等待游戏响应），进度条也一直在动，不会看起来卡死。
                Rectangle {
                    id: progressTrack
                    Layout.fillWidth: true
                    // 设计稿 .ov-progress{margin:8px 0 10px}：与阶段行留出间距，
                    // 否则 3px 细条会紧贴上面的文字，看起来像压住了一行。
                    Layout.topMargin: 8
                    Layout.preferredHeight: 3
                    radius: 2
                    color: '#141519'
                    clip: true

                    readonly property color fillColor: uiState.themeColor('green', uiState.appearance)

                    // ---- 确定进度：填充 + 流光 ----
                    Rectangle {
                        id: progressFill
                        height: progressTrack.height
                        radius: 2
                        color: progressTrack.fillColor
                        visible: overlayState.progress >= 0
                        // 至少有 4px，progress=0 时也看得到起点
                        width: Math.max(4, progressTrack.width * Math.max(0, Math.min(1, overlayState.progress)))
                        clip: true

                        Behavior on width {
                            NumberAnimation {
                                duration: uiState.motion('timer')
                                easing.type: Easing.OutCubic
                            }
                        }

                        // 常在流光：与进度数值无关，恒速来回
                        Rectangle {
                            id: sheen
                            width: Math.max(18, progressFill.width * 0.4)
                            height: parent.height
                            radius: 1
                            color: '#66FFFFFF'

                            SequentialAnimation on x {
                                loops: Animation.Infinite
                                running: overlayState.progress >= 0 && !overlayState.collapsed
                                PropertyAnimation {
                                    from: -sheen.width
                                    to: progressFill.width
                                    duration: 1500
                                    easing.type: Easing.InOutSine
                                }
                            }
                        }
                    }

                    // ---- 不确定进度：38% 滑块来回扫 ----
                    Rectangle {
                        id: progressSlide
                        height: progressTrack.height
                        radius: 2
                        color: progressTrack.fillColor
                        width: progressTrack.width * 0.38
                        visible: overlayState.progress < 0

                        SequentialAnimation on x {
                            loops: Animation.Infinite
                            running: overlayState.progress < 0 && !overlayState.collapsed
                            PropertyAnimation {
                                from: -progressSlide.width
                                to: progressTrack.width
                                duration: 1500
                                easing.type: Easing.InOutSine
                            }
                        }
                    }
                }

                // 说明
                Text {
                    Layout.fillWidth: true
                    Layout.topMargin: 10
                    text: overlayState.body
                    color: uiState.themeColor('muted_2', uiState.appearance)
                    font.pixelSize: 12
                    lineHeight: 1.65
                    wrapMode: Text.WordWrap
                }

                // 计时副行
                Text {
                    Layout.fillWidth: true
                    Layout.topMargin: 4
                    visible: overlayState.elapsed.length > 0
                    text: overlayState.elapsed
                    color: uiState.themeColor('faint', uiState.appearance)
                    font.pixelSize: 10
                    font.family: 'Consolas'
                }

                // ================= 不透明度（设计稿 .ov-settings） =================
                ColumnLayout {
                    id: opacityPanel
                    Layout.fillWidth: true
                    Layout.topMargin: 10
                    spacing: 4
                    visible: false

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 6
                        Text {
                            text: Loc.t('不透明度')
                            color: uiState.themeColor('muted', uiState.appearance)
                            font.pixelSize: 10
                        }
                        Item { Layout.fillWidth: true }
                        Text {
                            text: Math.round(alphaSlider.value * 100) + '%'
                            color: uiState.themeColor('muted_2', uiState.appearance)
                            font.pixelSize: 10
                            font.family: 'Consolas'
                        }
                    }

                    UiSlider {
                        id: alphaSlider
                        Layout.fillWidth: true
                        from: 0.65
                        to: 1.0
                        value: overlayBridge.opacity()
                        onMoved: function(v) { overlayBridge.setOpacity(v) }
                    }
                }

                // ================= 候选列表（设计稿 .cand） =================
                //   标题行（.cand__title）· 区域明细行（.cand__row）· 汇总行（.cand__sum）· 行动按钮（.pick）
                Flickable {
                    Layout.fillWidth: true
                    Layout.topMargin: 10
                    // 每张卡：标题 18 + 区域行 22×n + 汇总 16 + 按钮 28 + 间距/内边距
                    Layout.preferredHeight: Math.min(candList.implicitHeight, 360)
                    visible: overlayState.candidates.length > 0
                    contentHeight: candList.implicitHeight
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: UiScrollBar { }

                    ColumnLayout {
                        id: candList
                        width: parent.width
                        spacing: 8

                        Repeater {
                            model: overlayState.candidates
                            delegate: Rectangle {
                                id: candCard
                                Layout.fillWidth: true
                                implicitHeight: cardBody.implicitHeight + 20
                                radius: 8
                                color: modelData.picked
                                       ? uiState.themeColor('selected', uiState.appearance)
                                       : uiState.themeColor('pop', uiState.appearance)
                                border.width: 1
                                border.color: modelData.picked
                                              ? uiState.themeColor('green', uiState.appearance)
                                              : uiState.themeColor('pop_line', uiState.appearance)
                                Behavior on color { ColorAnimation { duration: 150 } }
                                Behavior on border.color { ColorAnimation { duration: 150 } }

                                ColumnLayout {
                                    id: cardBody
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    anchors.margins: 10
                                    spacing: 0

                                    // 标题
                                    Text {
                                        Layout.fillWidth: true
                                        text: modelData.title
                                        color: uiState.themeColor('muted', uiState.appearance)
                                        font.pixelSize: 11
                                        elide: Text.ElideRight
                                    }

                                    // 区域明细
                                    Repeater {
                                        model: modelData.details
                                        delegate: Item {
                                            Layout.fillWidth: true
                                            Layout.topMargin: 4
                                            implicitHeight: 20

                                            Rectangle {
                                                id: swatch
                                                width: 14
                                                height: 14
                                                radius: 3
                                                anchors.left: parent.left
                                                anchors.verticalCenter: parent.verticalCenter
                                                color: modelData.empty ? 'transparent'
                                                                       : modelData.hex
                                                border.width: 1
                                                border.color: modelData.empty
                                                              ? uiState.themeColor('faint', uiState.appearance)
                                                              : '#24FFFFFF'
                                            }

                                            Text {
                                                anchors.left: swatch.right
                                                anchors.leftMargin: 8
                                                anchors.verticalCenter: parent.verticalCenter
                                                text: modelData.name
                                                color: uiState.themeColor('muted', uiState.appearance)
                                                font.pixelSize: 11
                                            }

                                            Text {
                                                anchors.left: swatch.right
                                                anchors.leftMargin: 54
                                                anchors.verticalCenter: parent.verticalCenter
                                                text: modelData.empty ? Loc.t('未参与匹配') : modelData.hex
                                                color: modelData.empty
                                                       ? uiState.themeColor('faint', uiState.appearance)
                                                       : uiState.themeColor('text', uiState.appearance)
                                                font.pixelSize: 11
                                                font.family: 'Consolas'
                                            }

                                            Text {
                                                anchors.right: parent.right
                                                anchors.verticalCenter: parent.verticalCenter
                                                text: modelData.delta
                                                color: uiState.themeColor('muted_2', uiState.appearance)
                                                font.pixelSize: 10
                                                font.family: 'Consolas'
                                            }
                                        }
                                    }

                                    // 汇总
                                    Text {
                                        Layout.fillWidth: true
                                        Layout.topMargin: 6
                                        visible: modelData.summary.length > 0
                                        text: modelData.summary
                                        color: uiState.themeColor('faint', uiState.appearance)
                                        font.pixelSize: 10
                                        font.family: 'Consolas'
                                        elide: Text.ElideRight
                                    }

                                    // 行动按钮
                                    Rectangle {
                                        Layout.fillWidth: true
                                        Layout.topMargin: 8
                                        implicitHeight: 28
                                        radius: uiState.themeRadius('control', uiState.appearance)
                                        color: modelData.picked
                                               ? uiState.themeColor('green_soft', uiState.appearance)
                                               : (pickHover.hovered && !modelData.disabled
                                                  ? uiState.themeColor('btn_hover', uiState.appearance)
                                                  : uiState.themeColor('btn', uiState.appearance))
                                        border.width: 1
                                        border.color: modelData.picked
                                                      ? uiState.themeColor('green', uiState.appearance)
                                                      : uiState.themeColor('btn_line', uiState.appearance)

                                        Text {
                                            anchors.centerIn: parent
                                            text: modelData.disabled && !modelData.picked
                                                  ? Loc.t(modelData.action)
                                                  : Loc.t(modelData.action)
                                            color: modelData.picked
                                                   ? uiState.themeColor('green', uiState.appearance)
                                                   : (modelData.disabled
                                                      ? uiState.themeColor('faint', uiState.appearance)
                                                      : uiState.themeColor('text', uiState.appearance))
                                            font.pixelSize: 11
                                        }

                                        HoverHandler { id: pickHover }

                                        MouseArea {
                                            anchors.fill: parent
                                            cursorShape: modelData.disabled ? Qt.ArrowCursor
                                                                            : Qt.PointingHandCursor
                                            enabled: !modelData.disabled
                                            onClicked: overlayBridge.chooseCandidate(modelData.id)
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

            }

            // ================= 底部动作 =================
            RowLayout {
                id: actions
                Layout.fillWidth: true
                Layout.topMargin: overlayState.collapsed ? 0 : 10
                spacing: 6
                visible: !overlayState.collapsed

                // 停止 F9（高 34）
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 34
                    radius: uiState.themeRadius('control', uiState.appearance)
                    color: stopHover.hovered ? '#3A5D43' : uiState.themeColor('green_soft', uiState.appearance)
                    border.width: 1
                    border.color: uiState.themeColor('green_soft', uiState.appearance)

                    Row {
                        anchors.centerIn: parent
                        spacing: 6
                        Text {
                            text: overlayState.stopped ? Loc.t('已停止') : Loc.t('停止')
                            color: overlayState.stopped ? uiState.themeColor('muted', uiState.appearance)
                                                        : uiState.themeColor('text', uiState.appearance)
                            font.pixelSize: 12
                        }
                        Text {
                            visible: !overlayState.stopped
                            text: 'F9'
                            color: uiState.themeColor('muted_2', uiState.appearance)
                            font.pixelSize: 9
                            font.family: 'Consolas'
                        }
                    }

                    HoverHandler { id: stopHover }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        enabled: !overlayState.stopped
                        onClicked: overlayBridge.requestStop()
                    }
                }

                // 重新寻色 F7（高 30）
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 34
                    visible: overlayState.retryEnabled
                    radius: uiState.themeRadius('control', uiState.appearance)
                    color: retryHover.hovered ? '#2D313B' : uiState.themeColor('btn', uiState.appearance)
                    border.width: 1
                    border.color: uiState.themeColor('btn_line', uiState.appearance)

                    Row {
                        anchors.centerIn: parent
                        spacing: 6
                        Text {
                            text: Loc.t('重新寻色')
                            color: uiState.themeColor('muted_2', uiState.appearance)
                            font.pixelSize: 11
                        }
                        Text {
                            text: 'F7'
                            color: uiState.themeColor('faint', uiState.appearance)
                            font.pixelSize: 9
                            font.family: 'Consolas'
                        }
                    }

                    HoverHandler { id: retryHover }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: overlayBridge.requestRetry()
                    }
                }
            }

        }
    }
}