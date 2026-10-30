import QtQuick

// 圆角图片：把图片画进一个圆角矩形里。
//
// 为什么不用 Image + Rectangle.radius：`clip` 只裁矩形，图片会盖住圆角，
// 四角变回直角；`MultiEffect.maskSource` 在主窗口的卡片结构里实测无输出。
// Canvas 的 `clip()` 由 Qt 自己光栅化，任何尺寸/任何父级下都稳定，
// 而且颜色是铺到弧线为止——不会出现「角落没填满」的暗缝。
//
//   RoundedImage { anchors.fill: parent; radius: 12; source: card.paletteImage }
Item {
    id: root

    property url source
    property real radius: 12
    // 图片按控件尺寸拉伸（色板/色图需要铺满，不做等比留边）
    property bool stretch: true

    Image {
        id: img
        visible: false
        source: root.source
        asynchronous: false
    }

    Canvas {
        id: canvas
        anchors.fill: parent
        // Coalesce width/height/source updates into the next render frame.
        renderStrategy: Canvas.Cooperative

        onPaint: {
            var ctx = getContext('2d')
            ctx.reset()
            var w = width, h = height
            if (w <= 0 || h <= 0) return
            var r = Math.max(0, Math.min(root.radius, w / 2, h / 2))
            if (r > 0) {
                ctx.beginPath()
                ctx.moveTo(r, 0)
                ctx.lineTo(w - r, 0)
                ctx.arcTo(w, 0, w, r, r)
                ctx.lineTo(w, h - r)
                ctx.arcTo(w, h, w - r, h, r)
                ctx.lineTo(r, h)
                ctx.arcTo(0, h, 0, h - r, r)
                ctx.lineTo(0, r)
                ctx.arcTo(0, 0, r, 0, r)
                ctx.closePath()
                ctx.clip()
            }
            if (img.status === Image.Ready) {
                if (root.stretch) {
                    ctx.drawImage(img, 0, 0, w, h)
                } else {
                    var s = Math.min(w / img.sourceSize.width, h / img.sourceSize.height)
                    var dw = img.sourceSize.width * s
                    var dh = img.sourceSize.height * s
                    ctx.drawImage(img, (w - dw) / 2, (h - dh) / 2, dw, dh)
                }
            }
        }

        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        // 隐藏期间收到的 requestPaint 会被丢弃：重新可见时要再排一次，
        // 否则卡片刚拿到色板图时画布还是空的（实测过）。
        onVisibleChanged: if (visible) requestPaint()
        Component.onCompleted: requestPaint()

        Connections {
            target: img
            function onStatusChanged() { canvas.requestPaint() }
        }

        Connections {
            target: root
            function onSourceChanged() { canvas.requestPaint() }
            function onRadiusChanged() { canvas.requestPaint() }
        }
    }
}
