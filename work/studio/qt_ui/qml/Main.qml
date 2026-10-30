import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

// 主窗口 —— ui-spec-v7.md 3.1 / 3.2
//   页面内边距 24/16/18（左右/上/下）· 区块间距 9 · 内容宽 min(1400, 100%)
//   圆角 12：Window 透明 + 圆角矩形，四角外真正透明
//   透明度按需求不做
Window {
    id: root

    // 注意：state / bridge 由 Python setContextProperty 注入（名为 uiState / bridge），
    // 这里不能声明同名 property，否则会遮蔽上下文属性。

    readonly property int padSide: root.width <= 560 ? 10 : (root.width <= 980 ? 16 : 24)
    readonly property int padTop: 14
    readonly property int padBottom: 14

    // ---- V2 统一区块高度（单一来源，改这里就够）----
    readonly property int appBarH: root.narrow ? 40 + 32 : 40
    readonly property int envBarH: root.narrow ? 86 : 46
    readonly property int noteH: 12
    readonly property int runBarH: root.threeCol ? 108 : runStack.implicitHeight + 22
    readonly property int footerH: 12
    readonly property int pageGap: 9
    readonly property int cardMinH: 448

    // 卡片区高度 = 窗口高度 - 其余区块；不依赖 layout 回读，避免绑定环
    readonly property int cardsH: Math.max(
        cardMinH,
        root.height - padTop - padBottom - appBarH - envBarH - noteH
        - (root.threeCol ? runBarH : runStack.implicitHeight + 22) - footerH - pageGap * 5)

    // ---- 紧凑浮层：六个入口共用同一个 Popover ----
    //   anchorItem 在点击时记录，浮层贴着对应按钮弹出
    property Item panelAnchor: null
    property string panelKind: ''

    // 命令式驱动，**不要**给 quickPanel.open 写绑定：
    // Popover.close() 内部会 open = false，一旦 open 上存在绑定，
    // 这次赋值就会把绑定永久销毁，之后 panelKind 再怎么变都打不开
    // （复现：点按钮 → 点空白 → 再点按钮，open 恒为 false）。
    function openPanel(kind, anchor) {
        if (quickPanel.open && panelKind === kind) {
            quickPanel.close()
            return
        }
        // 先把锚点直接交给浮层，再开：
        // 之前写 root.panelAnchor = anchor 后立刻 show()，而 anchorItem 是绑定，
        // 属性绑定要等下一轮求值才刷新，show() 里的 _place() 可能仍按**上一次**
        // 的锚点算位置，于是浮层出现在上一个按钮附近。
        // 这里 anchorItem 不做绑定（见下方 Popover），显式赋值即时生效。
        panelAnchor = anchor
        panelKind = kind
        quickPanel.anchorItem = anchor
        quickPanel.show()
    }

    readonly property color bgColor: uiState.themeColor('bg', uiState.appearance)
    readonly property color textColor: uiState.themeColor('text', uiState.appearance)
    readonly property color mutedColor: uiState.themeColor('muted', uiState.appearance)
    readonly property color muted2: uiState.themeColor('muted_2', uiState.appearance)
    readonly property color lineColor: uiState.themeColor('line', uiState.appearance)
    readonly property color faintColor: uiState.themeColor('faint', uiState.appearance)

    // 断点（ui-spec-v7.md 第 9 节）
    readonly property bool threeCol: root.width > 980

    // 启动自检探针：确认 uiState 真的被注入且可调用。
    // 若 setContextProperty 的名字写错，uiState 会静默变成 undefined，
    // 界面不会报错、只会整体回退成浅色——用这个属性在启动时拦住。
    readonly property bool uiStateReady: {
        try {
            return uiState !== null && uiState !== undefined
                   && typeof uiState.themeColor === 'function'
                   && uiState.themeColor('bg', uiState.appearance).length > 0
        } catch (e) {
            return false
        }
    }
    readonly property bool narrow: root.width <= 560
    readonly property bool tiny: root.width < 400

    width: Math.min(1280, Screen.desktopAvailableWidth - 60)
    height: Math.min(752, Screen.desktopAvailableHeight - 80)
    minimumWidth: 360
    minimumHeight: 520
    // 更新后首次启动时保持隐藏，由 QtHost 在更新提交后显示
    visible: launchVisible
    // AppearAnim：窗口出场统一淡入
    NumberAnimation on opacity { from: 0; to: 1; duration: 150; easing.type: Easing.OutCubic }
    color: 'transparent'
    flags: Qt.Window | Qt.FramelessWindowHint | Qt.WindowMinimizeButtonHint
    // 标题栏关闭、任务栏关闭、Alt+F4 都交给 QtHost.close()：先停寻色、保存设置再退出
    // Qt 的 quit 也会发起窗口关闭。宿主完成停止与保存后须放行，
    // 否则第二次关闭仍被拒绝，按钮和更新器都无法让进程退出。
    property bool closeApproved: false
    onClosing: (close) => {
        close.accepted = root.closeApproved
        if (!root.closeApproved) bridge.requestClose()
    }
    title: Loc.t('染色工坊 · 瑪奇 Mobile')

    // ---------------------------------------------------------------------
    // 圆角底板
    // ---------------------------------------------------------------------
    Rectangle {
        id: surface
        objectName: 'surface'
        anchors.fill: parent
        radius: 12
        color: root.bgColor
        border.width: 1
        border.color: root.lineColor
        clip: true

        Flickable {
            id: pageScroll
            anchors.fill: parent
            anchors.leftMargin: root.padSide
            // 窄屏时内容会滚动，滚动条浮在右缘会压住顶栏按钮，预留 10px
            anchors.rightMargin: root.padSide + (root.narrow ? 10 : 0)
            anchors.topMargin: root.padTop
            anchors.bottomMargin: root.padBottom
            contentWidth: width
            contentHeight: Math.max(height, page.implicitHeight)
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            // 单列模式允许纵向滚动；三列在 1024 以上不应出现滚动条
            ScrollBar.vertical: UiScrollBar { }

            ColumnLayout {
                id: page
                width: Math.min(parent.width, 1400)
                x: Math.max(0, (parent.width - width) / 2)
                spacing: 9

                // ================= AppBar（高 40） =================
                Item {
                    objectName: 'appBar'
                    Layout.fillWidth: true
                    // 窄屏时操作按钮换到第二行（原型 .appbar{flex-wrap:wrap}）
                    implicitHeight: root.appBarH

                    // 窗口拖动带：仅顶栏左侧品牌区，避开右侧按钮。
                    // 无边框窗口需要它，但不能整窗覆盖，否则子控件收不到点击。
                    Item {
                        anchors.left: parent.left
                        anchors.top: parent.top
                        anchors.bottom: parent.bottom
                        width: Math.max(0, parent.width - windowControls.width
                                        - (root.narrow ? 0 : actionsRow.width + 6) - 40)
                        z: -1

                        DragHandler {
                            target: null
                            acceptedDevices: PointerDevice.Mouse
                            onActiveChanged: if (active) root.startSystemMove()
                        }
                    }

                    Row {
                        id: brandRow
                        anchors.left: parent.left
                        anchors.top: parent.top
                        height: 40
                        spacing: 9

                        // 品牌块 30×30，圆角 8，三根绿柱
                        Rectangle {
                            width: 28
                            height: 28
                            radius: 7
                            color: '#262933'
                            border.width: 1
                            border.color: '#343841'
                            anchors.verticalCenter: parent.verticalCenter

                            Row {
                                anchors.centerIn: parent
                                spacing: 2

                                Repeater {
                                    model: [0.45, 1.0, 0.7]
                                    delegate: Rectangle {
                                        width: 4
                                        height: 16 * modelData
                                        radius: 1
                                        color: uiState.themeColor('green', uiState.appearance)
                                        anchors.bottom: parent.bottom
                                        opacity: 0.55 + 0.45 * modelData
                                    }
                                }
                            }
                        }

                        Column {
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 1

                            Text {
                                text: Loc.t('染色工坊')
                                color: root.textColor
                                font.pixelSize: 15
                                font.weight: Font.DemiBold
                                font.letterSpacing: 0.6
                            }
                            Text {
                                text: Loc.t('瑪奇 Mobile') + '  /  by 南千和  ·  v'
                                      + uiState.appVersion
                                color: root.faintColor
                                font.pixelSize: 10
                                font.letterSpacing: 0.3
                            }
                        }
                    }

                    Row {
                        id: actionsRow
                        // 宽屏排在窗口控制左侧；窄屏换到第二行右对齐
                        anchors.right: root.narrow ? parent.right : windowControls.left
                        anchors.rightMargin: root.narrow ? 0 : 6
                        anchors.top: root.narrow ? brandRow.bottom : parent.top
                        anchors.topMargin: root.narrow ? 2 : 0
                        height: root.narrow ? 30 : 40
                        spacing: 6

                        // 主题切换：浅色 / 深色（原型未规定，按 4.1 令牌两列实现）
                        // 与右侧按钮同高（30）并垂直居中；Row 里不设 verticalCenter 会贴顶，
                        // 与旁边包在 30 高 Item 里的按钮错开 5px。
                        Item {
                            width: themeBtn.implicitWidth
                            height: 30
                            anchors.verticalCenter: parent.verticalCenter

                            UiButton {
                                id: themeBtn
                                objectName: 'themeBtn'
                                text: Loc.t(uiState.appearance === 'dark' ? '☾ 深色' : '☀ 浅色')
                                kind: 'secondary'
                                implicitHeight: 30
                                onClicked: bridge.toggleAppearance()
                            }
                        }

                        Repeater {
                            model: uiState.headerActions
                            delegate: Item {
                                width: hdrBtn.implicitWidth
                                height: 30
                                anchors.verticalCenter: parent.verticalCenter

                                UiButton {
                                    id: hdrBtn
                                    objectName: 'hdrBtn_' + modelData.key
                                    text: Loc.t(modelData.key === 'update' ? uiState.updateLabel
                                                                           : modelData.label)
                                    kind: modelData.kind
                                    implicitHeight: 30
                                    onClicked: {
                                        // tutorial / support 走紧凑浮层；
                                        // github 开浏览器，update 打开完整更新对话框
                                        if (modelData.key === 'github' || modelData.key === 'update') {
                                            bridge.headerAction(modelData.key)
                                        } else {
                                            root.openPanel(modelData.key, hdrBtn)
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // 窗口控制：无边框窗口自带最小化与关闭，始终固定在右上角
                    Row {
                        id: windowControls
                        anchors.right: parent.right
                        anchors.top: parent.top
                        height: 40
                        spacing: 6

                        Item {
                            width: minBtn.implicitWidth
                            height: 30
                            anchors.verticalCenter: parent.verticalCenter

                            UiButton {
                                id: minBtn
                                objectName: 'minimizeBtn'
                                text: '—'
                                kind: 'ghost'
                                implicitWidth: 32
                                implicitHeight: 30
                                onClicked: root.showMinimized()
                            }
                        }
                        Item {
                            width: closeBtn.implicitWidth
                            height: 30
                            anchors.verticalCenter: parent.verticalCenter

                            UiButton {
                                id: closeBtn
                                objectName: 'closeBtn'
                                text: '✕'
                                kind: 'ghost'
                                implicitWidth: 32
                                implicitHeight: 30
                                onClicked: root.close()
                            }
                        }
                    }
                }

                // ================= EnvironmentBar（高 50，内边距 8，圆角 8） =================
                //   宽屏：一行（窗口按钮 · 服务器 · 弹性 · 方案/记录 · 语言）
                //   窄屏：两行（原型 .environment{flex-wrap:wrap}）
                Rectangle {
                    id: envBarBox
                    objectName: 'envBar'
                    Layout.fillWidth: true
                    implicitHeight: root.envBarH
                    radius: 8
                    color: uiState.themeColor('panel', uiState.appearance)
                    border.width: 1
                    border.color: uiState.themeColor('panel_line', uiState.appearance)

                    // ---- 宽屏单行 ----
                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 7
                        spacing: 7
                        visible: !root.narrow

                        EnvWindowButton {
                            id: envWindowWide
                            objectName: 'envWindowWide'
                            Layout.maximumWidth: 380
                            Layout.fillWidth: true
                            Layout.preferredWidth: 260
                            onClicked: root.openPanel('window', envWindowWide)
                        }

                        UiCombo {
                            objectName: 'serverCombo'
                            Layout.preferredWidth: 110
                            model: uiState.serverValues
                            current: uiState.serverLabel
                            onActivated: function(v) { bridge.serverChanged(v) }
                        }

                        Item { Layout.fillWidth: true }

                        Repeater {
                            model: uiState.toolbarActions
                            delegate: UiButton {
                                id: toolBtnWide
                                objectName: 'toolBtn_' + modelData.key
                                text: Loc.t(modelData.label)
                                kind: modelData.kind
                                // 保存方案 / 寻色记录 → 紧凑浮层，不再开大窗口
                                onClicked: root.openPanel(modelData.key === 'save' ? 'presets' : 'history',
                                                          toolBtnWide)
                            }
                        }

                        UiCombo {
                            objectName: 'langCombo'
                            Layout.preferredWidth: 110
                            model: uiState.languages
                            current: uiState.language
                            translate: false
                            onActivated: function(v) { bridge.languageChanged(v) }
                        }
                    }

                    // ---- 窄屏两行 ----
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 8
                        spacing: 6
                        visible: root.narrow

                        EnvWindowButton {
                            id: envWindowNarrow
                            Layout.fillWidth: true
                            Layout.preferredHeight: 32
                            onClicked: root.openPanel('window', envWindowNarrow)
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            UiCombo {
                                Layout.preferredWidth: 88
                                model: uiState.serverValues
                                current: uiState.serverLabel
                                onActivated: function(v) { bridge.serverChanged(v) }
                            }

                            Item { Layout.fillWidth: true }

                            Repeater {
                                model: uiState.toolbarActions
                                delegate: UiButton {
                                    id: toolBtnNarrow
                                    objectName: 'toolBtnNarrow_' + modelData.key
                                    text: Loc.t(modelData.label)
                                    kind: modelData.kind
                                    onClicked: root.openPanel(modelData.key === 'save' ? 'presets' : 'history',
                                                              toolBtnNarrow)
                                }
                            }

                            UiCombo {
                                Layout.preferredWidth: 92
                                model: uiState.languages
                                current: uiState.language
                                onActivated: function(v) { bridge.languageChanged(v) }
                            }
                        }
                    }
                }

                // ================= 环境说明行（高 14） =================
                Item {
                    Layout.fillWidth: true
                    implicitHeight: root.noteH

                    RowLayout {
                        anchors.fill: parent
                        spacing: 10

                        Text {
                            text: Loc.t('支持台服；韩服和日服测试中。')
                            color: root.faintColor
                            font.pixelSize: 10
                        }

                        Item { Layout.fillWidth: true }

                        Text {
                            text: Loc.t(uiState.regionNote)
                            visible: uiState.regionNoteVisible
                            color: uiState.themeColor('amber', uiState.appearance)
                            font.pixelSize: 10
                        }
                    }
                }

                // ================= 三列区域卡 =================
                // 高度语义与原型一致：整数高度 481（ui-spec 3.2），
                // 不再用 fillHeight —— 那会让 page.implicitHeight 依赖自身
                // 高度，与 Flickable.contentHeight 形成绑定环，最终把卡片
                // 和运行栏一起压扁。
                Item {
                    objectName: 'cardsBlock'
                    id: cardsBlock
                    // 色板改为浮层后不再撑高卡片区
                    Layout.fillWidth: true
                    implicitHeight: root.threeCol
                                    ? root.cardsH
                                    : cardGrid.implicitHeight
                    Layout.preferredHeight: implicitHeight

                    // Resize only rearranges these three instances: no delegate
                    // destruction, focus loss or repeated entry animations.
                    Grid {
                        id: cardGrid
                        columns: root.threeCol ? 3 : 1
                        width: root.threeCol ? parent.width : Math.min(parent.width, 620)
                        anchors.horizontalCenter: parent.horizontalCenter
                        spacing: 10
                        Repeater {
                            model: [0, 1, 2]
                            delegate: RegionCard {
                                width: Math.max(0, (cardGrid.width - (cardGrid.columns - 1) * 10) / cardGrid.columns)
                                height: root.threeCol ? root.cardsH
                                    : 322 + Math.round((width - 28) * 265 / 688)
                                cardIndex: modelData
                                uiBridge: bridge
                            }
                        }
                    }
                }

                // ================= RunBar（340 + 自适应，间距 14，内边距 12/14） =================
                Rectangle {
                    objectName: 'runBar'
                    Layout.fillWidth: true
                    implicitHeight: root.runBarH
                    radius: uiState.themeRadius('card', uiState.appearance)
                    color: uiState.themeColor('panel', uiState.appearance)
                    border.width: 1
                    border.color: uiState.themeColor('panel_line', uiState.appearance)

                    // 三列布局：控制区 + 状态区
                    RowLayout {
                        id: runRow
                        anchors.fill: parent
                        anchors.topMargin: 10
                        anchors.bottomMargin: 10
                        anchors.leftMargin: 12
                        anchors.rightMargin: 12
                        spacing: 12
                        visible: root.threeCol

                        // ---- 控制区 300 ----
                        ColumnLayout {
                            objectName: 'runControls'
                            Layout.preferredWidth: 300
                            Layout.minimumWidth: 300
                            Layout.maximumWidth: 300
                            Layout.fillHeight: true
                            spacing: 7

                            RowLayout {
                                objectName: 'runButtons'
                                Layout.fillWidth: true
                                spacing: 7

                                UiButton {
                                    objectName: 'startBtn'
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 34
                                    text: Loc.t('开始  F8')
                                    kind: 'primary'
                                    enabled: uiState.startEnabled
                                    onClicked: bridge.start()
                                }

                                UiButton {
                                    objectName: 'stopBtn'
                                    Layout.preferredWidth: 84
                                    Layout.preferredHeight: 34
                                    text: Loc.t('停止  F9')
                                    kind: 'secondary'
                                    onClicked: bridge.stop()
                                }
                            }

                            UiCombo {
                                objectName: 'runStrategy'
                                Layout.fillWidth: true
                                Layout.preferredHeight: 26
                                model: uiState.strategyValues
                                current: uiState.strategyValue
                                translate: false
                                onActivated: function(v) { bridge.strategyChanged(v) }
                            }

                            Text {
                                Layout.fillWidth: true
                                text: Loc.t(uiState.strategyNote)
                                color: uiState.strategyWarn ? uiState.themeColor('amber', uiState.appearance) : root.mutedColor
                                font.pixelSize: 10
                                lineHeight: 1.45
                                wrapMode: Text.WordWrap
                            }

                            Item { Layout.fillHeight: true }
                        }

                        // 分隔线
                        Rectangle {
                            Layout.fillHeight: true
                            width: 1
                            color: uiState.themeColor('line', uiState.appearance)
                        }

                        // ---- 状态区 ----
                        ColumnLayout {
                            objectName: 'runStatus'
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            spacing: 3

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 7

                                Rectangle {
                                    width: 6
                                    height: 6
                                    radius: 3
                                    color: {
                                        if (uiState.statusTone === 'live') return uiState.themeColor('green', uiState.appearance)
                                        if (uiState.statusTone === 'warn') return uiState.themeColor('amber', uiState.appearance)
                                        if (uiState.statusTone === 'error') return uiState.themeColor('danger', uiState.appearance)
                                        return uiState.themeColor('faint', uiState.appearance)
                                    }
                                }

                                Text {
                                    Layout.fillWidth: true
                                    text: Loc.t(uiState.status)
                                    color: root.textColor
                                    font.pixelSize: 11
                                    font.weight: Font.Medium
                                    elide: Text.ElideRight
                                }

                                Text {
                                    text: Loc.t(uiState.logExpanded ? '收起' : '运行日志')
                                    color: root.mutedColor
                                    font.pixelSize: 10
                                    MouseArea {
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: bridge.toggleLog()
                                    }
                                }
                            }

                            Text {
                                Layout.fillWidth: true
                                text: Loc.t(uiState.detail)
                                visible: uiState.detailVisible
                                color: root.mutedColor
                                font.pixelSize: 10
                                elide: Text.ElideRight
                            }

                            // 运行日志：默认 2 行（34px），展开 112px
                            Flickable {
                                Layout.fillWidth: true
                                Layout.preferredHeight: uiState.logExpanded ? 112 : 34
                                visible: uiState.logLines.length > 0
                                contentHeight: logColumn.implicitHeight
                                clip: true
                                boundsBehavior: Flickable.StopAtBounds
                                Behavior on Layout.preferredHeight {
                                    NumberAnimation { duration: 180 }
                                }

                                Column {
                                    id: logColumn
                                    width: parent.width
                                    spacing: 2

                                    Repeater {
                                        model: uiState.logLines
                                        delegate: Row {
                                            width: logColumn.width
                                            spacing: 7
                                            Text {
                                                text: modelData.time
                                                color: root.mutedColor
                                                font.pixelSize: 9
                                                font.family: 'Consolas'
                                            }
                                            Text {
                                                width: logColumn.width - 50
                                                text: modelData.text
                                                color: root.faintColor
                                                font.pixelSize: 9
                                                font.family: 'Consolas'
                                                elide: Text.ElideRight
                                            }
                                        }
                                    }
                                }
                            }

                            Item { Layout.fillHeight: true }
                        }
                    }

                    // 单列：上下堆叠
                    ColumnLayout {
                        id: runStack
                        anchors.fill: parent
                        anchors.margins: 12
                        visible: !root.threeCol
                        spacing: 10

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            UiButton {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 34
                                text: Loc.t('开始  F8')
                                kind: 'primary'
                                enabled: uiState.startEnabled
                                onClicked: bridge.start()
                            }
                            UiButton {
                                Layout.preferredWidth: 84
                                Layout.preferredHeight: 34
                                text: Loc.t('停止  F9')
                                kind: 'secondary'
                                onClicked: bridge.stop()
                            }
                        }

                        UiCombo {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 26
                            model: uiState.strategyValues
                            current: uiState.strategyValue
                            translate: false
                            onActivated: function(v) { bridge.strategyChanged(v) }
                        }

                        Text {
                            Layout.fillWidth: true
                            text: Loc.t(uiState.strategyNote)
                            color: uiState.strategyWarn ? uiState.themeColor('amber', uiState.appearance) : root.mutedColor
                            font.pixelSize: 10
                            wrapMode: Text.WordWrap
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 7
                            Rectangle {
                                width: 6; height: 6; radius: 3
                                color: uiState.statusTone === 'live' ? uiState.themeColor('green', uiState.appearance)
                                      : uiState.statusTone === 'warn' ? uiState.themeColor('amber', uiState.appearance)
                                      : uiState.themeColor('faint', uiState.appearance)
                            }
                            Text {
                                Layout.fillWidth: true
                                text: Loc.t(uiState.status)
                                color: root.textColor
                                font.pixelSize: 11
                                wrapMode: Text.WordWrap
                            }
                        }

                        Text {
                            Layout.fillWidth: true
                            text: Loc.t(uiState.detail)
                            visible: uiState.detailVisible
                            color: root.mutedColor
                            font.pixelSize: 10
                            wrapMode: Text.WordWrap
                        }
                    }
                }

                // ================= Footer（高 13） =================
                Item {
                    objectName: 'footer'
                    Layout.fillWidth: true
                    implicitHeight: root.footerH

                    RowLayout {
                        anchors.fill: parent
                        spacing: 16

                        Text {
                            Layout.fillWidth: true
                            text: Loc.t(uiState.footer)
                            color: root.faintColor
                            font.pixelSize: 9
                            elide: Text.ElideRight
                        }
                    }
                }
            }
        }

        // -----------------------------------------------------------------
        // Native resizing uses stable screen coordinates and OS DPI handling.
        // -----------------------------------------------------------------
        Repeater {
            model: [Qt.LeftEdge, Qt.RightEdge, Qt.TopEdge, Qt.BottomEdge,
                    Qt.LeftEdge | Qt.TopEdge, Qt.RightEdge | Qt.TopEdge,
                    Qt.LeftEdge | Qt.BottomEdge, Qt.RightEdge | Qt.BottomEdge]
            delegate: MouseArea {
                required property int modelData
                objectName: 'resizeEdge_' + modelData
                readonly property bool leftEdge: (modelData & Qt.LeftEdge) !== 0
                readonly property bool rightEdge: (modelData & Qt.RightEdge) !== 0
                readonly property bool topEdge: (modelData & Qt.TopEdge) !== 0
                readonly property bool bottomEdge: (modelData & Qt.BottomEdge) !== 0
                readonly property bool corner: (leftEdge || rightEdge) && (topEdge || bottomEdge)
                z: corner ? 102 : 101
                width: corner ? 12 : ((leftEdge || rightEdge) ? 6 : parent.width - 24)
                height: corner ? 12 : ((topEdge || bottomEdge) ? 6 : parent.height - 24)
                x: rightEdge ? parent.width - width : (leftEdge ? 0 : 12)
                y: bottomEdge ? parent.height - height : (topEdge ? 0 : 12)
                cursorShape: corner ? ((leftEdge === topEdge) ? Qt.SizeFDiagCursor : Qt.SizeBDiagCursor)
                                    : ((leftEdge || rightEdge) ? Qt.SizeHorCursor : Qt.SizeVerCursor)
                property bool fallbackResize: false
                property point pointerOrigin
                property rect geometryOrigin
                onPressed: function(mouse) {
                    fallbackResize = !root.startSystemResize(modelData)
                    if (fallbackResize) {
                        pointerOrigin = mapToGlobal(mouse.x, mouse.y)
                        geometryOrigin = Qt.rect(root.x, root.y, root.width, root.height)
                    }
                }
                onPositionChanged: function(mouse) {
                    if (!pressed || !fallbackResize) return
                    var pointer = mapToGlobal(mouse.x, mouse.y)
                    var dx = pointer.x - pointerOrigin.x, dy = pointer.y - pointerOrigin.y
                    var w = Math.max(root.minimumWidth, geometryOrigin.width + (rightEdge ? dx : leftEdge ? -dx : 0))
                    var h = Math.max(root.minimumHeight, geometryOrigin.height + (bottomEdge ? dy : topEdge ? -dy : 0))
                    root.width = w
                    root.height = h
                    if (leftEdge) root.x = geometryOrigin.x + geometryOrigin.width - w
                    if (topEdge) root.y = geometryOrigin.y + geometryOrigin.height - h
                }
                onReleased: fallbackResize = false
                onCanceled: fallbackResize = false
            }
        }
    }

    // ================= 紧凑浮层（六个入口共用） =================
    //
    // 取代原来的「新建窗口」：锚点就是被点击的按钮，浮层贴着它弹出，
    // 方向由 Popover 按可用空间自动选（下方优先）。
    Popover {
        id: quickPanel
        objectName: 'quickPanelPopover'
        // 锚点由 openPanel() 显式赋值（见上），不写绑定：
        // 绑定会因命令式赋值被破坏，而且求值时机晚于 show()，导致位置滞后一次。
        // 遮罩从入口栏下沿开始，这样浮层开着时点另一个入口能直接切换。
        // 用布局常量算，而不是 mapToItem：绑定里调用 mapToItem 不会依赖
        // 祖先的布局变化，只在创建时算一次，拿到的是布局完成前的值（46）。
        topInset: root.padTop + root.appBarH + root.pageGap + root.envBarH
        // open 由 openPanel/close 命令式控制，见上方注释
        contentWidth: panelContent.implicitWidth
        contentHeight: panelContent.implicitHeight

        QuickPanel {
            id: panelContent
            kind: root.panelKind
            // 面板内的「点选即完成」操作（选窗口 / 载入方案）要真正关掉浮层：
            // 只清 panelKind 不会关浮层（open 已是命令式，不再跟随 kind），
            // 结果留下一个 kind 为空、标题兜底成「检查更新」的空壳浮层。
            onClosed: {
                root.panelKind = ''
                quickPanel.close()
            }
        }

        // 关闭时（点外部 / Esc / 再次点同一按钮）清掉 kind，
        // 否则 kind 残留会让「同按钮切换」判断失效
        onOpenChanged: if (!open && root.panelKind !== '') root.panelKind = ''
    }

    // 无边框窗口拖动：**只在顶栏这块空白区域**生效。
    //
    // 之前把 DragHandler 挂在 Window 根级，它会抢占整个窗口的指针事件，
    // 结果所有按钮、输入框、下拉都收不到点击（实测 bridge.stop 调用 0 次）。
    // 现在改成顶栏内一个透明拖拽带，并在下方叠加 dragArea 承接拖动。
}
