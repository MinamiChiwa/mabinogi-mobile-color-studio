import QtQuick
import QtQuick.Controls

// 通用浮层基座 —— 依据锚点在屏幕上的位置自动选择弹出方向
//
//   · 优先向下；下方放不下且上方够 → 向上；上下都不够时比较左右，向侧边弹；
//   · 可用区 = 窗口矩形 ∩ 当前屏幕可用区，窗口贴着屏幕边缘也不会弹到屏幕外；
//   · 入场/出场带方向位移 + 缩放 + 淡入，位移方向与 placement 一致。
//
// 用法：
//   Popover {
//       id: p
//       anchorItem: someSwatch
//       contentWidth: 320; contentHeight: 372
//       InlineColorPicker { ... }
//   }
//
// 注意：浮层不参与卡片布局。RegionCard 里把它 parent 到窗口 contentItem，
// 这样弹出时不会挤压卡片高度，也不会被 Flickable 裁掉。
Item {
    id: pop

    // ---- 输入 ----
    property Item anchorItem: null
    property bool open: false
    property int gap: 8               // 与锚点的间距
    property int edge: 10             // 与可用区边缘的最小距离
    property int contentWidth: 320
    property int contentHeight: 360
    // 遮罩顶部留白：把入口栏让出来，浮层打开时仍能直接点其它入口切换，
    // 而不是「先关掉再点开」。默认 0，其它浮层（色板等）行为不变。
    property real topInset: 0
    // 方向优先级：第一个放得下的方向即采用；都放不下时取空间最大的一侧
    property var order: ['below', 'right', 'above', 'left']

    // 只读：最近一次计算出的方向，供子项决定动画方向
    property string placement: 'below'

    default property alias contentData: host.data

    anchors.fill: parent
    z: 900
    // 关闭时让位给正常交互；出场动画期间仍可见但不吃点击
    visible: open || panel.opacity > 0.02
    enabled: open

    function _geom() {
        if (!anchorItem) return null
        var win = pop.Window.window
        if (!win) return null
        var p = anchorItem.mapToItem(null, 0, 0)
        var ax = p.x, ay = p.y, aw = anchorItem.width, ah = anchorItem.height

        var left = edge, top = edge
        var right = win.width - edge, bottom = win.height - edge

        // 屏幕可用区换算到窗口坐标；多屏时即锚点所在屏
        var scr = win.screen ? win.screen.availableGeometry : null
        if (scr) {
            left = Math.max(left, scr.x - win.x + edge)
            top = Math.max(top, scr.y - win.y + edge)
            right = Math.min(right, scr.x + scr.width - win.x - edge)
            bottom = Math.min(bottom, scr.y + scr.height - win.y - edge)
        }

        return {
            ax: ax, ay: ay, aw: aw, ah: ah,
            left: left, top: top, right: right, bottom: bottom,
            below: bottom - (ay + ah + gap),
            above: (ay - gap) - top,
            rightSpace: right - (ax + aw + gap),
            leftSpace: (ax - gap) - left
        }
    }

    function _fits(dir, g, w, h) {
        if (dir === 'below') return g.below >= h - 12
        if (dir === 'above') return g.above >= h - 12
        if (dir === 'right') return g.rightSpace >= w - 12
        return g.leftSpace >= w - 12
    }

    function _place() {
        var g = _geom()
        if (!g) return
        var w = contentWidth, h = contentHeight

        var dir = ''
        for (var i = 0; i < order.length; i++) {
            if (_fits(order[i], g, w, h)) { dir = order[i]; break }
        }
        if (!dir) {
            // 都放不下：选空间最大的一侧，内容自己滚动
            var spaces = { below: g.below, above: g.above,
                           right: g.rightSpace, left: g.leftSpace }
            dir = order[0]
            for (var k in spaces) {
                if (spaces[k] > spaces[dir] + 24) dir = k
            }
        }
        placement = dir

        var x, y
        if (dir === 'below') {
            x = g.ax + g.aw / 2 - w / 2
            y = g.ay + g.ah + gap
        } else if (dir === 'above') {
            x = g.ax + g.aw / 2 - w / 2
            y = g.ay - gap - h
        } else if (dir === 'right') {
            x = g.ax + g.aw + gap
            y = g.ay + g.ah / 2 - h / 2
        } else {
            x = g.ax - gap - w
            y = g.ay + g.ah / 2 - h / 2
        }

        var tx = Math.max(g.left, Math.min(x, g.right - w))
        var ty = Math.max(g.top, Math.min(y, g.bottom - h))
        panel.x = tx
        panel.y = ty
        // 记下目标值，Behavior 动画期间读取 panel.x 得到的是中间值
        _targetX = tx
        _targetY = ty

        // 入场位移：从「点击位置」滑到最终位置。
        // 取锚点中心与面板中心的差向量，限制在面板自身尺寸的 45%（且不超过 170px），
        // 这样无论面板离点击点多远，观感都是从点击处「长出来」而不是从远处飞入。
        var acx = g.ax + g.aw / 2
        var acy = g.ay + g.ah / 2
        var pcx = tx + w / 2
        var pcy = ty + h / 2
        _slideX = Math.max(-170, Math.min(170, (acx - pcx) * 0.55))
        _slideY = Math.max(-170, Math.min(170, (acy - pcy) * 0.55))
    }

    // 入场滑动向量（关闭态相对目标位置的偏移）
    property real _slideX: 0
    property real _slideY: 0

    // 最后一次的目标坐标（供测试/调试读取）
    property real _targetX: 0
    property real _targetY: 0

    function show() {
        _place()
        open = true
        backdrop.forceActiveFocus()
    }

    function close() {
        open = false
    }

    function toggle() {
        if (open) close()
        else show()
    }

    onOpenChanged: if (open) _place()
    onContentHeightChanged: if (open) _place()
    onContentWidthChanged: if (open) _place()

    Connections {
        target: pop.anchorItem
        enabled: pop.open
        function onXChanged() { pop._place() }
        function onYChanged() { pop._place() }
        function onWidthChanged() { pop._place() }
        function onHeightChanged() { pop._place() }
    }

    Connections {
        target: pop.Window.window
        enabled: pop.open
        function onWidthChanged() { pop._place() }
        function onHeightChanged() { pop._place() }
        function onXChanged() { pop._place() }
        function onYChanged() { pop._place() }
    }

    // 点击外部关闭；Esc 同样关闭
    MouseArea {
        id: backdrop
        anchors.fill: parent
        anchors.topMargin: pop.topInset
        enabled: pop.open
        acceptedButtons: Qt.AllButtons
        onClicked: pop.close()
        Keys.onEscapePressed: pop.close()
        focus: pop.open
    }

    // 浮层面板
    Rectangle {
        id: panel
        objectName: 'popoverPanel'

        width: pop.contentWidth
        height: pop.contentHeight
        radius: uiState.themeRadius('dialog', uiState.appearance)
        color: uiState.themeColor('pop', uiState.appearance)
        border.width: 1
        border.color: uiState.themeColor('pop_line', uiState.appearance)

        opacity: pop.open ? 1 : 0
        scale: pop.open ? 1 : 0.94
        visible: opacity > 0.02

        // 从点击位置朝弹出方向滑出：关闭态停在靠近锚点的一侧，
        // 打开时滑到最终位置（方向由 _place() 依屏幕可用区决定）。
        transform: Translate {
            x: pop.open ? 0 : pop._slideX
            y: pop.open ? 0 : pop._slideY
            Behavior on x { NumberAnimation { duration: pop.open ? 230 : 140; easing.type: Easing.OutCubic } }
            Behavior on y { NumberAnimation { duration: pop.open ? 230 : 140; easing.type: Easing.OutCubic } }
        }

        // 缩放原点朝向锚点，看起来是从点击处展开
        transformOrigin: pop.placement === 'below' ? Item.Top
                       : pop.placement === 'above' ? Item.Bottom
                       : pop.placement === 'right' ? Item.Left : Item.Right

        Behavior on opacity { NumberAnimation { duration: pop.open ? 170 : 120 } }
        Behavior on scale { NumberAnimation { duration: 230; easing.type: Easing.OutCubic } }
        Behavior on x { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
        Behavior on y { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }

        // 内容承载
        Item {
            id: host
            anchors.fill: parent
            anchors.margins: 12
            clip: true
        }

        // 投影（不影响布局，仅视觉）
        Rectangle {
            anchors.fill: parent
            anchors.margins: -1
            radius: parent.radius + 1
            color: 'transparent'
            border.width: 1
            border.color: '#18000000'
            z: -1
        }
    }
}
