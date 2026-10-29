import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// 紧凑浮层内容：按 kind 渲染六种小面板。
//
// 取代原来的独立窗口（自动检测 / 支持作者 / 检查更新 / 使用教程 /
// 保存方案 / 寻色记录）。所有数据都来自 Bridge 的 *Rows() 槽，
// 这里不判断任何业务规则，只负责排版与转发点击。
Item {
    id: panel

    property string kind: ''

    // 由外层 Popover 读取：内容自适应
    // 期望的面板总宽：Popover 会再扣掉左右各 12 的内边距，
    // 所以这里 300 对应实际可用内容宽 276。
    implicitWidth: 300
    // 高度同理：+24 补偿 Popover 的上下内边距，+4 是圆角余量
    implicitHeight: Math.min(body.implicitHeight + 28, 470)

    // 关键：宽度跟随宿主，而不是用自己的 implicitWidth。
    // 否则在宽度 276 的 host 里按 300 排版，内容会向右溢出 12px，
    // 右侧按钮/文字就被面板边缘切掉（各语言都中招，不只是英文）。
    width: parent ? parent.width : implicitWidth
    height: implicitHeight

    // ---- 各面板的数据 ----
    property var rows: []

    function reload() {
        if (!bridge) {
            rows = []
            return
        }
        if (kind === 'window') rows = bridge.windowRows()
        else if (kind === 'presets') rows = bridge.presetRows()
        else if (kind === 'history') rows = bridge.historyRows()
        else if (kind === 'tutorial') rows = bridge.tutorialRows()
        else rows = []
    }

    onKindChanged: {
        reload()
        kindFade.restart()
    }

    // 面板内容切换：淡入 + 2px 上移，避免整块内容突兀跳变
    opacity: 1
    SequentialAnimation {
        id: kindFade
        NumberAnimation { target: panel; property: 'opacity'; to: 0.35; duration: 0 }
        NumberAnimation { target: panel; property: 'opacity'; to: 1; duration: 150; easing.type: Easing.OutCubic }
    }
    transform: Translate { y: 0 }

    readonly property color cText: uiState.themeColor('text', uiState.appearance)
    readonly property color cMuted: uiState.themeColor('muted', uiState.appearance)
    readonly property color cMuted2: uiState.themeColor('muted_2', uiState.appearance)
    readonly property color cFaint: uiState.themeColor('faint', uiState.appearance)
    readonly property color cGreen: uiState.themeColor('green', uiState.appearance)
    readonly property color cLine: uiState.themeColor('line', uiState.appearance)
    readonly property color cPop: uiState.themeColor('pop', uiState.appearance)
    readonly property color cPopLine: uiState.themeColor('pop_line', uiState.appearance)
    readonly property color cBtn: uiState.themeColor('btn', uiState.appearance)

    ColumnLayout {
        id: body
        // 不参与外层宽度推导：宽度由 anchors 决定，避免子项的隐式宽度
        // 把浮层撑宽、导致右侧按钮被挤出边界
        implicitWidth: 0
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        // 内边距已由 Popover 的 host 提供（12px），这里不再叠加
        spacing: 8

        // ================= 标题行 =================
        // 标题负责让位（fillWidth + elide），刷新按钮保持自身宽度：
        // 之前两者都在 RowLayout 里，标题的隐式宽度把刷新挤到只剩几个像素，
        // 任何语言都显示不全（English 也只显示 "Refre"）。
        RowLayout {
            id: titleRow
            objectName: 'qpTitleRow'
            Layout.fillWidth: true
            spacing: 8

            Text {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                // 显式映射：未知 kind（例如关闭过程中的空值）返回空串。
                // 之前用三元兜底成「检查更新」，于是空壳浮层看起来像多弹了一个更新窗。
                text: {
                    switch (panel.kind) {
                    case 'window':   return Loc.t('游戏窗口')
                    case 'presets':  return Loc.t('保存方案')
                    case 'history':  return Loc.t('寻色记录')
                    case 'tutorial': return Loc.t('使用教程')
                    case 'support':  return Loc.t('支持作者')
                    case 'update':   return Loc.t('检查更新')
                    }
                    return ''
                }
                color: panel.cText
                font.pixelSize: 12
                font.weight: Font.DemiBold
                elide: Text.ElideRight
            }

            // 刷新：固定按文字宽度排版，hover 有底色过渡
            Rectangle {
                id: refreshBtn
                objectName: 'qpRefreshBtn'
                Layout.alignment: Qt.AlignVCenter
                implicitWidth: refreshLabel.implicitWidth + 14
                implicitHeight: 20
                // 关键：不允许被压缩，否则文字会被裁
                Layout.minimumWidth: implicitWidth
                Layout.preferredWidth: implicitWidth
                visible: panel.kind === 'window'
                radius: 5
                color: refreshHover.hovered ? panel.cPop : 'transparent'
                border.width: 1
                border.color: refreshHover.hovered ? panel.cLine : 'transparent'

                Behavior on color { ColorAnimation { duration: 140 } }
                Behavior on border.color { ColorAnimation { duration: 140 } }

                Text {
                    id: refreshLabel
                    anchors.centerIn: parent
                    text: Loc.t('刷新')
                    color: refreshHover.hovered ? panel.cText : panel.cMuted2
                    font.pixelSize: 10
                    Behavior on color { ColorAnimation { duration: 140 } }
                }

                HoverHandler { id: refreshHover }

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: panel.reload()
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: panel.cLine
        }

        // ================= 游戏窗口 =================
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 4
            visible: panel.kind === 'window'

            Text {
                Layout.fillWidth: true
                visible: panel.rows.length === 0
                text: Loc.t('未检测到游戏窗口')
                color: panel.cFaint
                font.pixelSize: 11
                topPadding: 6
                bottomPadding: 6
            }

            Flickable {
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(winList.implicitHeight, 220)
                visible: panel.rows.length > 0
                contentHeight: winList.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds

                ColumnLayout {
                    id: winList
                    width: parent.width
                    spacing: 4

            Repeater {
                model: panel.kind === 'window' ? panel.rows : []
                delegate: Rectangle {
                    id: winRow
                    objectName: 'winRow_' + index
                    Layout.fillWidth: true
                    implicitHeight: 30
                    radius: 6
                    color: winHover.hovered && modelData.ready ? panel.cPop : 'transparent'
                    border.width: 1
                    border.color: winHover.hovered && modelData.ready ? panel.cPopLine : panel.cLine
                    Behavior on color { ColorAnimation { duration: 140 } }
                    Behavior on border.color { ColorAnimation { duration: 140 } }
                    scale: winArea.pressed ? 0.985 : 1.0
                    Behavior on scale { NumberAnimation { duration: 110; easing.type: Easing.OutCubic } }

                    Text {
                        anchors.left: parent.left
                        anchors.leftMargin: 8
                        anchors.right: parent.right
                        anchors.rightMargin: 8
                        anchors.verticalCenter: parent.verticalCenter
                        text: modelData.title
                        color: modelData.ready ? panel.cText : panel.cFaint
                        font.pixelSize: 11
                        elide: Text.ElideRight
                    }

                    HoverHandler { id: winHover }
                    MouseArea {
                        id: winArea
                        anchors.fill: parent
                        cursorShape: modelData.ready ? Qt.PointingHandCursor : Qt.ArrowCursor
                        enabled: modelData.ready
                        onClicked: {
                            bridge.chooseWindow(modelData.hwnd)
                            panel.reload()
                            panel.closed()
                        }
                    }
                }
            }
                }
            }
        }

        // ================= 保存方案 =================
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 6
            visible: panel.kind === 'presets'

            // 输入框独占一行，保存按钮单独右对齐：
            // 原先「输入框 + 按钮」同一行，行内最小宽度会顶出面板右边界。
            UiField {
                id: presetName
                Layout.fillWidth: true
                implicitHeight: 28
                placeholder: Loc.t('新方案名称')
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 6

                Item { Layout.fillWidth: true }

                UiButton {
                    text: Loc.t('保存')
                    kind: 'primary'
                    implicitHeight: 28
                    implicitWidth: 56
                    onClicked: {
                        var err = bridge.savePreset(presetName.text)
                        presetMsg.text = err === '' ? Loc.t('已保存') : err
                        presetMsg.color = err === '' ? panel.cGreen : panel.cFaint
                        presetName.text = ''
                        panel.reload()
                    }
                }
            }

            Text {
                id: presetMsg
                Layout.fillWidth: true
                text: ''
                color: panel.cFaint
                font.pixelSize: 10
                visible: text.length > 0
            }

            Text {
                Layout.fillWidth: true
                visible: panel.rows.length === 0
                text: Loc.t('还没有保存的方案')
                color: panel.cFaint
                font.pixelSize: 11
            }

            // 方案列表：最多 5 条，超出滚动
            Flickable {
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(presetList.implicitHeight, 150)
                visible: panel.rows.length > 0
                contentHeight: presetList.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds

                ColumnLayout {
                    id: presetList
                    width: parent.width
                    spacing: 4

                    Repeater {
                        model: panel.kind === 'presets' ? panel.rows : []
                        delegate: Rectangle {
                            id: presetRow
                            Layout.fillWidth: true
                            implicitHeight: 34
                            radius: 6
                            color: preHover.hovered ? panel.cPop : 'transparent'
                            border.width: 1
                            border.color: preHover.hovered ? panel.cPopLine : panel.cLine
                            Behavior on color { ColorAnimation { duration: 140 } }
                            Behavior on border.color { ColorAnimation { duration: 140 } }

                            Column {
                                anchors.left: parent.left
                                anchors.leftMargin: 8
                                anchors.right: actions2.left
                                anchors.rightMargin: 6
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 0
                                Text {
                                    width: parent.width
                                    text: modelData.name
                                    color: panel.cText
                                    font.pixelSize: 11
                                    elide: Text.ElideRight
                                }
                                Text {
                                    width: parent.width
                                    text: modelData.summary
                                    color: panel.cFaint
                                    font.pixelSize: 9
                                    font.family: 'Consolas'
                                    elide: Text.ElideRight
                                }
                            }

                            Row {
                                id: actions2
                                anchors.right: parent.right
                                anchors.rightMargin: 6
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 8

                                Text {
                                    text: Loc.t('载入')
                                    color: panel.cMuted2
                                    font.pixelSize: 10
                                    MouseArea {
                                        anchors.fill: parent
                                        anchors.margins: -4
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: {
                                            var err = bridge.applyPreset(modelData.id)
                                            presetMsg.text = err
                                            presetMsg.color = panel.cFaint
                                            if (err === '') panel.closed()
                                        }
                                    }
                                }
                                Text {
                                    text: Loc.t('删除')
                                    color: panel.cFaint
                                    font.pixelSize: 10
                                    MouseArea {
                                        anchors.fill: parent
                                        anchors.margins: -4
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: {
                                            bridge.deletePreset(modelData.id)
                                            panel.reload()
                                        }
                                    }
                                }
                            }

                            HoverHandler { id: preHover }
                        }
                    }
                }
            }
        }

        // ================= 寻色记录 =================
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 4
            visible: panel.kind === 'history'

            Text {
                Layout.fillWidth: true
                visible: panel.rows.length === 0
                text: Loc.t('还没有寻色记录')
                color: panel.cFaint
                font.pixelSize: 11
            }

            Flickable {
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(histList.implicitHeight, 170)
                visible: panel.rows.length > 0
                contentHeight: histList.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds

                ColumnLayout {
                    id: histList
                    width: parent.width
                    spacing: 3

                    Repeater {
                        model: panel.kind === 'history' ? panel.rows : []
                        delegate: Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: 32
                            radius: 6
                            color: 'transparent'
                            border.width: 1
                            border.color: panel.cLine

                            Column {
                                anchors.left: parent.left
                                anchors.leftMargin: 8
                                anchors.right: parent.right
                                anchors.rightMargin: 8
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 0
                                Text {
                                    width: parent.width
                                    text: modelData.time + '  ·  ' + (modelData.outcome || '')
                                    color: panel.cMuted2
                                    font.pixelSize: 10
                                    elide: Text.ElideRight
                                }
                                Text {
                                    width: parent.width
                                    text: (modelData.maximum !== null && modelData.maximum !== undefined
                                           ? '最大 ' + Number(modelData.maximum).toFixed(2) : '')
                                        + (modelData.average !== null && modelData.average !== undefined
                                           ? ' / 平均 ' + Number(modelData.average).toFixed(2) : '')
                                    color: panel.cFaint
                                    font.pixelSize: 9
                                    font.family: 'Consolas'
                                    elide: Text.ElideRight
                                }
                            }
                        }
                    }
                }
            }
        }

        // ================= 使用教程 =================
        //
        // 用普通 Column + 显式 width，而不是 ColumnLayout：
        // 中文没有空格，Text.WordWrap 不会断行，隐式宽度会把内容顶出面板；
        // WrapAtWordBoundaryOrAnywhere 才能在中文字符间断行。
        Flickable {
            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(tutList.height, 300)
            visible: panel.kind === 'tutorial'
            // 显式给出 contentWidth：否则 Flickable 会按内容宽度扩张，
            // 文本按更大的宽度排版后再被裁掉，末尾字符会被切半个。
            contentWidth: width
            contentHeight: tutList.height
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: UiScrollBar { }

            Column {
                id: tutList
                width: parent.width
                spacing: 10

                Repeater {
                    model: panel.kind === 'tutorial' ? panel.rows : []
                    delegate: Column {
                        width: tutList.width
                        spacing: 2

                        Text {
                            width: tutList.width - 8
                            text: modelData.h
                            color: panel.cText
                            font.pixelSize: 11
                            font.weight: Font.DemiBold
                            wrapMode: Text.WrapAtWordBoundaryOrAnywhere
                        }
                        Text {
                            width: tutList.width - 8
                            text: modelData.b
                            color: panel.cMuted2
                            font.pixelSize: 10
                            lineHeight: 1.5
                            wrapMode: Text.WrapAtWordBoundaryOrAnywhere
                        }
                    }
                }

                UiButton {
                    width: parent.width
                    text: Loc.t('提交问题 / Issues')
                    kind: 'secondary'
                    implicitHeight: 26
                    onClicked: bridge.openLink(bridge.supportLinks().issues)
                }
            }
        }

        // ================= 支持作者 =================
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 6
            visible: panel.kind === 'support'

            Text {
                Layout.fillWidth: true
                Layout.preferredWidth: 0
                text: Loc.t('赞助完全自愿，不论是否赞助都能使用全部功能。')
                color: panel.cMuted2
                font.pixelSize: 10
                lineHeight: 1.5
                wrapMode: Text.WordWrap
            }

            Repeater {
                model: panel.kind === 'support'
                       ? [{ k: 'afdian', label: '爱发电' },
                          { k: 'patreon', label: 'Patreon' },
                          { k: 'github', label: 'GitHub' }]
                       : []
                delegate: Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: 28
                    radius: 6
                    color: supHover.hovered ? panel.cPop : 'transparent'
                    border.width: 1
                    border.color: supHover.hovered ? panel.cPopLine : panel.cLine
                    Behavior on color { ColorAnimation { duration: 140 } }
                    Behavior on border.color { ColorAnimation { duration: 140 } }
                    scale: supArea.pressed ? 0.985 : 1.0
                    Behavior on scale { NumberAnimation { duration: 110; easing.type: Easing.OutCubic } }

                    Text {
                        anchors.centerIn: parent
                        text: modelData.label
                        color: panel.cText
                        font.pixelSize: 11
                    }
                    HoverHandler { id: supHover }
                    MouseArea {
                        id: supArea
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: bridge.openLink(bridge.supportLinks()[modelData.k])
                    }
                }
            }
        }

        // ================= 检查更新 =================
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 6
            visible: panel.kind === 'update'

            Text {
                id: updateLabel
                Layout.fillWidth: true
                property var info: ({})
                text: info.label || Loc.t('当前版本已是最新')
                color: panel.cMuted2
                font.pixelSize: 11
                wrapMode: Text.WordWrap
            }

            UiButton {
                Layout.fillWidth: true
                text: Loc.t('检查更新')
                kind: 'secondary'
                implicitHeight: 28
                onClicked: {
                    if (!bridge) return
                    bridge.checkUpdate()
                    Qt.callLater(function() { updateLabel.info = bridge.updateInfo() })
                }
            }
        }
    }

    // 由外层注入：关闭自身
    signal closed()
}
