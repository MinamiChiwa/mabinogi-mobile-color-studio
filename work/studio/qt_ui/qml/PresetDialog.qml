import QtQuick
import QtQuick.Window
import QtQuick.Layouts
import QtQuick.Controls

// 染色方案：圆角 12，三区域可编辑
Window {
    id: root

    property string selectedId: ''
    property string message: ''
    property bool messageIsError: false
    property var editing: ({})

    width: 720
    height: 620
    // 由 window_fx 定位后 show()，避免先出现在系统默认位置再跳
    visible: false
    color: 'transparent'
    flags: Qt.Window | Qt.FramelessWindowHint
    title: Loc.t('染色方案')

    function refreshFrom(profile) {
        var p = (profile && profile.regions) ? profile : presetBridge.current()
        // 深拷贝：编辑时改的是副本，取消不会污染宿主
        editing = JSON.parse(JSON.stringify(p))
    }

    function clone(o) { return JSON.parse(JSON.stringify(o)) }

    function setRegion(i, key, value) {
        var p = clone(editing)
        p.regions[i][key] = value
        editing = p
    }

    function regionRank(i) {
        var order = editing.priority_order || [0, 1, 2]
        var r = order.indexOf(i)
        return r < 0 ? i + 1 : r + 1
    }

    // 与主界面的「同优先级互换」一致：交换名次，不改其它区域
    function setRank(i, rank) {
        var p = clone(editing)
        var order = (p.priority_order || [0, 1, 2]).slice()
        var j = order[rank - 1]
        var old = order.indexOf(i)
        if (j === i || old < 0) return
        order[old] = j
        order[rank - 1] = i
        p.priority_order = order
        editing = p
    }

    function setStrategy(v) {
        var p = clone(editing)
        p.search_strategy = v
        editing = p
    }

    function buildProfile() { return editing }

    Component.onCompleted: {
        refreshFrom({})
        presetBridge.message.connect(function(text, isError) {
            root.message = text
            root.messageIsError = isError
        })
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
                        text: Loc.t('染色方案')
                        color: uiState.themeColor('text', uiState.appearance)
                        font.pixelSize: 16
                        font.weight: Font.DemiBold
                    }
                    Text {
                        text: Loc.t('当前设置自动保存。这里可命名保存多套方案，也可单独编辑方案。')
                        color: uiState.themeColor('muted', uiState.appearance)
                        font.pixelSize: 11
                    }
                }
                Item { Layout.fillWidth: true }
                UiButton { text: '✕'; implicitWidth: 32; onClicked: root.close() }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                UiCombo {
                    id: chooser
                    Layout.preferredWidth: 240
                    model: {
                        void presetBridge.changed
                        var names = ['新方案']
                        var rows = presetBridge.presetNames()
                        for (var i = 0; i < rows.length; i++) names.push(rows[i].name)
                        return names
                    }
                    current: '新方案'
                    onActivated: function(v) {
                        var rows = presetBridge.presetNames()
                        for (var i = 0; i < rows.length; i++) {
                            if (rows[i].name === v) {
                                root.selectedId = rows[i].id
                                root.refreshFrom(presetBridge.presetProfile(rows[i].id))
                                return
                            }
                        }
                        root.selectedId = ''
                        root.refreshFrom({})
                    }
                }

                UiField {
                    id: nameField
                    Layout.fillWidth: true
                    placeholder: Loc.t('方案名称')
                }
            }

            Flickable {
                Layout.fillWidth: true
                Layout.fillHeight: true
                contentHeight: regionList.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: UiScrollBar { }

                ColumnLayout {
                    id: regionList
                    width: parent.width
                    spacing: 8

                    Repeater {
                        model: editing.regions ? editing.regions.length : 0
                        delegate: Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: 134
                            radius: 10
                            color: uiState.themeColor('panel', uiState.appearance)
                            border.width: 1
                            border.color: uiState.themeColor('line', uiState.appearance)

                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: 10
                                spacing: 6

                                // 第 1 行：启用 · 区域 N · 优先级
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 8

                                    UiCheck {
                                        // UiCheck 是 RowLayout，默认会吃掉整行宽度，
                                        // 限宽后「区域 N」才会紧跟在复选框右侧
                                        Layout.maximumWidth: 20
                                        Layout.alignment: Qt.AlignVCenter
                                        checked: !!editing.regions[index].enabled
                                        onToggled: function(v) { root.setRegion(index, 'enabled', v) }
                                    }

                                    Text {
                                        Layout.alignment: Qt.AlignVCenter
                                        text: Loc.t('区域') + ' ' + (index + 1)
                                        color: uiState.themeColor('text', uiState.appearance)
                                        font.pixelSize: 12
                                        font.weight: Font.DemiBold
                                    }

                                    Item { Layout.fillWidth: true }

                                    Text {
                                        text: Loc.t('优先级')
                                        color: uiState.themeColor('muted', uiState.appearance)
                                        font.pixelSize: 10
                                    }
                                    UiCombo {
                                        Layout.preferredWidth: 52
                                        implicitHeight: 26
                                        model: ['1', '2', '3']
                                        current: String(root.regionRank(index))
                                        onActivated: function(v) { root.setRank(index, parseInt(v)) }
                                    }
                                }

                                // 第 2 行：目标色 · 颜色要求 · 容差
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 6

                                    Text { text: Loc.t('目标色'); color: uiState.themeColor('muted', uiState.appearance); font.pixelSize: 10 }
                                    UiField {
                                        Layout.fillWidth: true
                                        fieldHeight: 28
                                        text: editing.regions[index].target
                                        onEdited: function(v) { editing.regions[index].target = v }
                                    }

                                    Text { text: Loc.t('颜色要求'); color: uiState.themeColor('muted', uiState.appearance); font.pixelSize: 10 }
                                    UiCombo {
                                        Layout.preferredWidth: 92
                                        implicitHeight: 28
                                        model: ['精准 HEX', '相似颜色']
                                        current: editing.regions[index].mode
                                        onActivated: function(v) { root.setRegion(index, 'mode', v) }
                                    }

                                    Text { text: Loc.t('容差'); color: uiState.themeColor('muted', uiState.appearance); font.pixelSize: 10 }
                                    UiField {
                                        Layout.preferredWidth: 48
                                        fieldHeight: 28
                                        text: String(editing.regions[index].tolerance)
                                        onEdited: function(v) { editing.regions[index].tolerance = Number(v) || 1 }
                                    }
                                }

                                // 第 3 行：替代色
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 6
                                    Text { text: Loc.t('替代色'); color: uiState.themeColor('muted', uiState.appearance); font.pixelSize: 10 }
                                    UiField {
                                        Layout.fillWidth: true
                                        fieldHeight: 28
                                        text: editing.regions[index].alt
                                        placeholder: '#FFFFFF, #EAEAEA'
                                        onEdited: function(v) { editing.regions[index].alt = v }
                                    }
                                }
                            }
                        }
                    }

                    // 寻色方式：整份方案的属性
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Text {
                            text: Loc.t('寻色方式')
                            color: uiState.themeColor('muted', uiState.appearance)
                            font.pixelSize: 10
                        }
                        UiCombo {
                            Layout.preferredWidth: 170
                            implicitHeight: 28
                            model: ['截图寻色', '精准寻色']
                            current: (editing.search_strategy === 'native') ? '精准寻色' : '截图寻色'
                            onActivated: function(v) {
                                root.setStrategy(v === '精准寻色' ? 'native' : 'screenshot')
                            }
                        }
                        Text {
                            text: Loc.t('精准寻色会读取游戏内存，风险较高')
                            color: uiState.themeColor('faint', uiState.appearance)
                            font.pixelSize: 9
                        }
                        Item { Layout.fillWidth: true }
                    }
                }
            }

            Text {
                Layout.fillWidth: true
                text: root.message
                visible: root.message.length > 0
                color: root.messageIsError ? uiState.themeColor('danger', uiState.appearance)
                                           : uiState.themeColor('accent', uiState.appearance)
                font.pixelSize: 11
                wrapMode: Text.WordWrap
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                UiButton {
                    text: root.selectedId ? Loc.t('保存修改') : Loc.t('保存新方案')
                    kind: 'primary'
                    onClicked: {
                        if (presetBridge.saveProfile(nameField.text, root.selectedId,
                                                     root.buildProfile())) {
                            root.selectedId = ''
                            nameField.text = ''
                        }
                    }
                }

                UiButton {
                    text: Loc.t('载入到主界面')
                    enabled: root.selectedId.length > 0
                    onClicked: if (presetBridge.load(root.selectedId)) root.refreshFrom({})
                }

                UiButton {
                    text: Loc.t('删除方案')
                    enabled: root.selectedId.length > 0
                    onClicked: {
                        if (presetBridge.remove(root.selectedId)) {
                            root.selectedId = ''
                            root.refreshFrom({})
                        }
                    }
                }

                Item { Layout.fillWidth: true }

                UiButton {
                    text: Loc.t('用当前设置新建')
                    onClicked: {
                        root.selectedId = ''
                        root.refreshFrom({})
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