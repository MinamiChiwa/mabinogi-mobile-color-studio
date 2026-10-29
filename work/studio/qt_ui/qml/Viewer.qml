import QtQuick
import QtQuick.Window
import QtQuick.Controls
import QtQuick.Layouts

// 完整允许色图查看器：圆角 + 缩放/拖动 + 悬停读色
Window {
    id: root

    property var sourceImage: null
    property real scaleFactor: 1.0
    property string hoverHex: ''

    width: 1000
    height: 740
    // 由 window_fx 定位后 show()，避免先出现在系统默认位置再跳
    visible: false
    color: 'transparent'
    flags: Qt.Window | Qt.FramelessWindowHint
    title: viewerTarget + Loc.t(' · 完整色图')

    Rectangle {
        anchors.fill: parent
        radius: 12
        color: uiState.themeColor('bg', uiState.appearance)
        border.width: 1
        border.color: uiState.themeColor('line', uiState.appearance)
        clip: true

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 18
            spacing: 10

            RowLayout {
                Layout.fillWidth: true
                Text {
                    text: viewerTarget + ' · ' + viewerCount.toLocaleString() + Loc.t(' 种允许颜色')
                    color: uiState.themeColor('text', uiState.appearance)
                    font.pixelSize: 14
                    font.weight: Font.DemiBold
                }
                Item { Layout.fillWidth: true }
                UiButton { text: Loc.t('适合窗口'); onClicked: root.fit() }
                UiButton { text: Loc.t('原始尺寸'); onClicked: root.scaleFactor = 1.0 }
                UiButton { text: '＋'; implicitWidth: 34; onClicked: root.scaleFactor = Math.min(8, root.scaleFactor * 2) }
                UiButton { text: '－'; implicitWidth: 34; onClicked: root.scaleFactor = Math.max(0.1, root.scaleFactor / 2) }
                UiButton { text: Loc.t('关闭'); onClicked: root.close() }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                radius: 8
                color: uiState.themeColor('field', uiState.appearance)
                clip: true

                Flickable {
                    id: view
                    anchors.fill: parent
                    contentWidth: Math.max(width, image.width * root.scaleFactor)
                    contentHeight: Math.max(height, image.height * root.scaleFactor)
                    boundsBehavior: Flickable.StopAtBounds
                    clip: true

                    Image {
                        id: image
                        source: root.sourceImage ? '' : ''
                        width: implicitWidth * root.scaleFactor
                        height: implicitHeight * root.scaleFactor
                        smooth: false
                        // sourceImage 是 QImage，用 sourceComponent 无法直接绑，
                        // 这里由 Python 侧设置到 image.source 上
                    }
                }
            }

            Text {
                text: root.hoverHex || Loc.t('拖动浏览 · 悬停查看色值')
                color: uiState.themeColor('muted', uiState.appearance)
                font.pixelSize: 11
            }
        }
    }

    function fit() {
        if (image.implicitWidth <= 0) return
        var need = Math.min((width - 60) / image.implicitWidth,
                            (height - 140) / image.implicitHeight)
        scaleFactor = Math.max(0.1, Math.min(8, need))
    }
}