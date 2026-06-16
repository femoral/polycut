import QtQuick
import QtQuick.Controls.Basic
import Polycut

// A themed unit dropdown. Reads the unit list from the bridge; emits the picked
// unit so the parent can write it back. Numeric/unit text is mono. (§6)
ComboBox {
    id: control
    property string unit: ""
    signal unitPicked(string u)

    model: processor.units
    currentIndex: Math.max(0, model.indexOf(unit))
    onActivated: control.unitPicked(model[currentIndex])

    implicitHeight: Theme.rowHeight
    font.family: Theme.fontMono
    font.pixelSize: Theme.fontBase

    contentItem: Text {
        leftPadding: Theme.gap
        text: control.displayText
        color: Theme.fg0
        font: control.font
        verticalAlignment: Text.AlignVCenter
    }
    indicator: Text {
        x: control.width - width - Theme.gap
        y: (control.height - height) / 2
        text: "▾"
        color: Theme.fg2
        font.family: Theme.fontUi
        font.pixelSize: Theme.fontSmall
    }
    background: Rectangle {
        radius: Theme.rMd
        color: Theme.bg2
        border.color: control.activeFocus || control.popup.visible ? Theme.teal : Theme.hairline
        border.width: Theme.borderThin
    }

    popup: Popup {
        y: control.height + Theme.gapXs
        width: control.width
        padding: Theme.borderThin
        background: Rectangle {
            radius: Theme.rSm
            color: Theme.bg2
            border.color: Theme.hairline
            border.width: Theme.borderThin
        }
        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: control.popup.visible ? control.delegateModel : null
            currentIndex: control.highlightedIndex
        }
    }
    delegate: ItemDelegate {
        required property var modelData
        required property int index
        width: control.width
        implicitHeight: Theme.rowHeight
        contentItem: Text {
            leftPadding: Theme.gap
            text: modelData
            color: Theme.fg1
            font.family: Theme.fontMono
            font.pixelSize: Theme.fontBase
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle {
            color: control.highlightedIndex === index ? Theme.bg3 : Theme.transparent
        }
    }
}
