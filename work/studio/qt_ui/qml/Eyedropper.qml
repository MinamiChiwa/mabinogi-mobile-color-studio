import QtQuick
import QtQuick.Window

// 屏幕吸管 —— 铺满虚拟桌面，冻结画面 + 十字光标 + 跟随标签
// 单击取色 · Esc / 右键取消
// 画面来自 Python 的 ImageProvider（1:1 物理像素），不做任何缩放或平滑
Window {
    id: root

    property int pixelWidth: 1
    property int pixelHeight: 1
    property string hoverHex: ''
    property bool labelFlipX: false
    property bool labelFlipY: false
    property real cursorX: 0
    property real cursorY: 0

    visible: false
    color: '#000000'
    flags: Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus
    title: Loc.t('屏幕吸管')
    // 窗口本身不抢焦点
    Component.onCompleted: requestActivate === undefined ? undefined : undefined

    // 冻结画面
    Image {
        id: frozen
        anchors.fill: parent
        source: 'image://frozen/desktop'
        fillMode: Image.Stretch
        smooth: false
        cache: false
        asynchronous: false
    }

    // 十字光标
    Item {
        anchors.fill: parent

        Rectangle {
            width: 1
            height: parent.height
            x: Math.round(root.cursorX)
            color: '#B3FFFFFF'
        }
        Rectangle {
            height: 1
            width: parent.width
            y: Math.round(root.cursorY)
            color: '#B3FFFFFF'
        }

        // 中心取色点（空心方框，标示实际采样像素）
        Rectangle {
            width: 9
            height: 9
            radius: 0
            color: 'transparent'
            border.width: 1
            border.color: '#000000'
            x: Math.round(root.cursorX) - 4
            y: Math.round(root.cursorY) - 4
        }
        Rectangle {
            width: 7
            height: 7
            color: 'transparent'
            border.width: 1
            border.color: '#FFFFFF'
            x: Math.round(root.cursorX) - 3
            y: Math.round(root.cursorY) - 3
        }
    }

    // 跟随标签：正方形色块预览 + 色值（样式参考设计图：深色圆角胶囊）
    //   只显示「色块 + HEX」两件东西，不放颜色中文名、也不放操作提示，
    //   保证标签足够小、不遮挡取色点附近的画面。
    //   色块是正方形（圆角 4），紧挨准星，随鼠标移动；
    //   靠近屏幕边缘时整体翻到另一侧，色块不会跑出屏幕。
    Rectangle {
        id: badge
        visible: root.hoverHex.length > 0
        width: badgeRow.implicitWidth + 24
        height: 40
        radius: 8
        // 底板保持中性深色：颜色由左侧正方形色块表达，避免整块染色后
        // 色块与底板同色、看不出边界
        color: '#F2262A33'
        border.width: 1
        border.color: '#33FFFFFF'

        x: root.labelFlipX
           ? Math.round(root.cursorX) - width - 18
           : Math.round(root.cursorX) + 18
        y: root.labelFlipY
           ? Math.round(root.cursorY) - height - 18
           : Math.round(root.cursorY) + 18

        Row {
            id: badgeRow
            anchors.centerIn: parent
            spacing: 10

            // 正方形色块预览（跟随准星，随 hoverHex 实时变色）
            Rectangle {
                id: swatch
                width: 24
                height: 24
                radius: 4
                color: root.hoverHex.length > 0 ? root.hoverHex : '#000000'
                border.width: 1
                border.color: '#59FFFFFF'
                anchors.verticalCenter: parent.verticalCenter

                // 内描边压一层深色，浅色底上也能看清方块边界
                Rectangle {
                    anchors.fill: parent
                    anchors.margins: 1
                    radius: 3
                    color: 'transparent'
                    border.width: 1
                    border.color: '#33000000'
                }
            }

            Text {
                text: root.hoverHex.toUpperCase()
                color: '#F2F4F8'
                font.pixelSize: 14
                font.family: 'Consolas'
                font.weight: Font.DemiBold
                font.letterSpacing: 0.4
                anchors.verticalCenter: parent.verticalCenter
            }
        }
    }

    // 输入
    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.CrossCursor
        acceptedButtons: Qt.LeftButton | Qt.RightButton

        onPositionChanged: function(mouse) {
            root.cursorX = mouse.x
            root.cursorY = mouse.y
            var hex = eyedropper.preview(mouse.x, mouse.y)
            root.hoverHex = hex || ''
            // 边缘翻转：按标签实际尺寸算，贴到右/下边缘时翻到另一侧
            root.labelFlipX = mouse.x + badge.width + 18 > root.width
            root.labelFlipY = mouse.y + badge.height + 18 > root.height
        }

        onClicked: function(mouse) {
            if (mouse.button === Qt.RightButton) {
                eyedropper.cancel()
            } else {
                eyedropper.confirm()
            }
        }
    }

    // Esc 取消（键盘不一定有焦点，Python 侧另有 GetAsyncKeyState 轮询兜底）
    Shortcut {
        sequence: 'Esc'
        onActivated: eyedropper.cancel()
    }
}