import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// 目标色集合预览面板（浮层内容，不含窗口边框）
//
//   · 默认铺满整个可视区（颜色必须填满窗口，不留黑边）
//   · 可 1:1 / 放大 / 缩小，放大后拖动查看
//   · 圆角由 RoundedImage（Canvas clip）裁出：颜色铺到弧线为止，
//     不会像 Rectangle.clip 那样把图片裁成直角
//   · 「在窗口中打开」交给原来的查看器窗口（带悬停读色）
Item {
    id: panel

    property var card: ({})
    property var bridge
    property int cardIndex: 0

    readonly property string source: (card && card.atlasImage) ? card.atlasImage : ''
    readonly property int imgW: (card && card.atlasWidth) ? card.atlasWidth : 0
    readonly property int imgH: (card && card.atlasHeight) ? card.atlasHeight : 0

    // 数量与模式都来自状态（不拼接已翻译的整句，避免无法切换语言）
    readonly property int count: (card && card.atlasCount) ? card.atlasCount : 0
    readonly property string noteText: {
        if (!count) return ''
        var key = (count === 1) ? '%1 色（单）' : '%1 色'
        var colors = Loc.t(key).replace('%1', Number(count).toLocaleString())
        return (card && card.exact)
               ? Loc.t('精准 HEX') + ' · ' + colors
               : 'ΔE ≤ ' + Math.round(card.tolerance || 8) + ' · ' + colors
    }

    property real zoom: 0          // 0 = 铺满
    readonly property bool fitted: zoom <= 0
    readonly property int corner: 12

    implicitWidth: 320
    implicitHeight: 260
    ColumnLayout {
        id: body
        anchors.fill: parent
        spacing: 8

        RowLayout {
            id: head
            Layout.fillWidth: true
            spacing: 6

            Text {
                text: Loc.t('目标色集合')
                color: uiState.themeColor('muted_2', uiState.appearance)
                font.pixelSize: 11
            }

            Text {
                Layout.fillWidth: true
                text: panel.noteText
                color: uiState.themeColor('faint', uiState.appearance)
                font.pixelSize: 10
                font.family: 'Consolas'
                elide: Text.ElideRight
            }

            UiButton {
                text: Loc.t('适合')
                compact: true
                implicitWidth: 44
                onClicked: panel.zoom = 0
            }
            UiButton {
                text: '1:1'
                compact: true
                implicitWidth: 40
                onClicked: panel.zoom = 1
            }
            UiButton {
                text: '＋'
                compact: true
                implicitWidth: 28
                onClicked: panel.zoom = Math.min(6, Math.max(panel.imgW / Math.max(1, panel.width),
                                                             panel.imgH / Math.max(1, panel.height)) * 1.5)
            }
            UiButton {
                id: lastBtn
                text: '－'
                compact: true
                implicitWidth: 28
                onClicked: panel.zoom = Math.max(0.2, panel.zoom <= 0 ? 0.8 : panel.zoom / 1.5)
            }
        }

        // ---- 颜色区：铺满可用空间，四角圆角 ----
        Item {
            id: frameWrap
            Layout.fillWidth: true
            Layout.fillHeight: true

            Rectangle {
                id: frameBg
                anchors.fill: parent
                radius: panel.corner
                color: uiState.themeColor('track_off', uiState.appearance)
                border.width: 0
            }

            // 铺满模式：Canvas 裁圆角，颜色一直铺到弧线，四角不留缝
            RoundedImage {
                objectName: 'atlasFill'
                anchors.fill: parent
                radius: panel.corner
                source: panel.source
                visible: panel.fitted && panel.source !== ''
            }

            // 放大模式：可拖动浏览。视口同样要圆角——否则放大后
            // Flickable 的方形 clip 会让色图四角变回直角。
            Item {
                id: viewport
                anchors.fill: parent
                clip: true
                visible: !panel.fitted

                Flickable {
                    id: view
                    anchors.fill: parent
                    contentWidth: Math.max(width, canvas.width)
                    contentHeight: Math.max(height, canvas.height)
                    boundsBehavior: Flickable.StopAtBounds
                    clip: true

                    Item {
                        id: canvas
                        width: Math.max(1, panel.imgW * panel.zoom)
                        height: Math.max(1, panel.imgH * panel.zoom)
                        x: Math.max(0, (view.width - width) / 2)
                        y: Math.max(0, (view.height - height) / 2)

                        // 放大后图片自身也要圆角，与铺满模式观感一致
                        RoundedImage {
                            anchors.fill: parent
                            radius: panel.corner
                            source: panel.source
                        }
                    }
                }
            }

            Text {
                anchors.centerIn: parent
                visible: panel.source === ''
                text: Loc.t('暂无可用颜色')
                color: uiState.themeColor('faint', uiState.appearance)
                font.pixelSize: 11
            }

            // 1px 描边画在最上层，保证图片铺满时边框仍在
            Rectangle {
                anchors.fill: parent
                radius: panel.corner
                color: 'transparent'
                border.width: 1
                border.color: uiState.themeColor('line', uiState.appearance)
            }
        }

        RowLayout {
            id: foot
            Layout.fillWidth: true
            spacing: 6

            Text {
                Layout.fillWidth: true
                text: panel.noteText
                color: uiState.themeColor('faint', uiState.appearance)
                font.pixelSize: 9
                font.family: 'Consolas'
                elide: Text.ElideRight
            }

            UiButton {
                text: Loc.t('在窗口中打开')
                compact: true
                implicitWidth: 104
                onClicked: if (panel.bridge) panel.bridge.openViewer(panel.cardIndex)
            }
        }
    }
}
