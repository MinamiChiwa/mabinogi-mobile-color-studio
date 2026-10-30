import QtQuick
import QtQuick.Controls

// 容差滑杆 —— ui-spec-v7.md 7.3 / 原型 .slider
//   轨道高 3、圆角 2；已完成段 --green，未完成 #2A2C33
//   滑块 13px 圆点 #E3E5EA；禁用时滑块 #5A616C、轨道全灰
//   滚轮不改变数值，避免滚动页面时误改容差
Item {
    id: slider

    property real from: 1
    property real to: 35
    property real value: 8
    property bool enabled: true

    signal moved(real value)

    implicitHeight: 18
    readonly property real ratio: Math.max(0, Math.min(1, (value - from) / Math.max(0.0001, to - from)))

    readonly property color fillColor: enabled
        ? uiState.themeColor('green', uiState.appearance)
        : uiState.themeColor('track', uiState.appearance)
    readonly property color thumbColor: enabled
        ? '#E3E5EA'
        : '#5A616C'

    // 轨道
    Rectangle {
        id: track
        anchors.verticalCenter: parent.verticalCenter
        width: parent.width
        height: 3
        radius: 2
        color: uiState.themeColor('track', uiState.appearance)

        Rectangle {
            width: parent.width * slider.ratio
            height: parent.height
            radius: 2
            color: slider.fillColor
        }
    }

    // 滑块
    Rectangle {
        id: thumb
        width: 13
        height: 13
        radius: 6.5
        x: Math.max(0, Math.min(track.width - width, track.width * slider.ratio - width / 2))
        anchors.verticalCenter: parent.verticalCenter
        color: slider.thumbColor
        border.width: 0

        // 原型 box-shadow: 0 1px 3px rgba(0,0,0,.5)
        Rectangle {
            anchors.fill: parent
            anchors.margins: -1
            radius: parent.radius + 1
            color: 'transparent'
            border.width: 1
            border.color: '#80000000'
            z: -1
        }

        // 聚焦环：0 0 0 3px rgba(93,194,100,.35)
        Rectangle {
            anchors.fill: parent
            anchors.margins: -3
            radius: parent.radius + 3
            color: 'transparent'
            border.width: 3
            border.color: '#595DC264'
            visible: mouse.containsMouse && slider.enabled
        }
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        anchors.topMargin: -6
        anchors.bottomMargin: -6
        cursorShape: Qt.PointingHandCursor
        enabled: slider.enabled
        hoverEnabled: true
        preventStealing: true

        function apply(posX) {
            var r = Math.min(1, Math.max(0, posX / track.width))
            var v = slider.from + r * (slider.to - slider.from)
            slider.moved(Math.round(v))
        }

        onPressed: function(m) { apply(m.x) }
        onPositionChanged: function(m) { if (pressed) apply(m.x) }

        // 滚轮显式不处理：防止悬停时误改色差
        onWheel: function(w) { w.accepted = false }
    }
}