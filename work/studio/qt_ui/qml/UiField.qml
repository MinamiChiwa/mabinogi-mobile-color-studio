import QtQuick
import QtQuick.Controls

// HEX / 文本输入 —— ui-spec-v7.md 7.3
//   高 36 · 圆角 6 · 等宽 14 · 字距 0.07em
//   hover 描边 #343740 · focus 描边 #41454F + 2px 浅环
//   非法：#8C4A46 描边 / #D8918C 文字
Item {
    id: field

    property string text: ''
    property string placeholder: ''
    property bool enabled: true
    property bool invalid: false
    property bool mono: true
    property int fieldHeight: 36

    signal edited(string value)

    implicitHeight: fieldHeight
    readonly property int animBase: uiState.motion('base')

    Rectangle {
        id: box
        anchors.fill: parent
        radius: uiState.themeRadius('control', uiState.appearance)
        color: uiState.themeColor('field', uiState.appearance)
        border.width: 1
        border.color: {
            if (field.invalid) return '#8C4A46'
            if (input.activeFocus) return '#41454F'
            if (hover.hovered && field.enabled) return '#343740'
            return uiState.themeColor('field_line', uiState.appearance)
        }
        Behavior on border.color { ColorAnimation { duration: field.animBase } }

        // focus 时的 2px 浅环（原型 box-shadow: 0 0 0 2px rgba(227,229,234,.06)）
        Rectangle {
            anchors.fill: parent
            anchors.margins: -2
            radius: uiState.themeRadius('control', uiState.appearance) + 2
            color: 'transparent'
            border.width: 2
            border.color: '#0FE3E5EA'
            visible: input.activeFocus && !field.invalid
        }

        TextInput {
            id: input
            anchors.fill: parent
            anchors.leftMargin: 12
            anchors.rightMargin: 12
            verticalAlignment: TextInput.AlignVCenter
            color: field.invalid ? '#D8918C' : uiState.themeColor('text', uiState.appearance)
            font.pixelSize: 14
            font.family: field.mono ? 'Consolas' : 'Microsoft YaHei UI'
            font.letterSpacing: field.mono ? 1.0 : 0
            selectByMouse: true
            enabled: field.enabled
            clip: true
            selectionColor: '#2F4C36'
            selectedTextColor: uiState.themeColor('text', uiState.appearance)

            // 输入即回写：外部读 `field.text` 才能拿到用户刚输入的内容。
            // 只发信号不回写，会让「添加替代色」这类按钮读到的永远是空串。
            text: field.text
            onTextEdited: {
                field.text = text
                field.edited(text)
            }

            // 外部改 text（清空、回填、重置）时同步到输入框
            Connections {
                target: field
                function onTextChanged() {
                    if (input.text !== field.text) input.text = field.text
                }
            }

            Text {
                anchors.fill: parent
                verticalAlignment: Text.AlignVCenter
                text: field.placeholder
                color: uiState.themeColor('faint', uiState.appearance)
                font: input.font
                visible: input.text.length === 0
            }
        }

        HoverHandler { id: hover }
    }
}