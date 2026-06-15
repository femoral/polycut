import QtQuick
import QtQuick.Layouts
import Polycut

// A right-inspector section: uppercase letter-spaced header + stacked content.
// (design-system.md §2, §4)
ColumnLayout {
    id: root
    property string title: ""
    default property alias content: holder.data

    Layout.fillWidth: true
    spacing: Theme.gap

    Text {
        text: root.title.toUpperCase()
        color: Theme.fg2
        font.family: Theme.fontUi
        font.pixelSize: Theme.fontSmall
        font.letterSpacing: Theme.headerSpacing
        font.bold: true
    }

    ColumnLayout {
        id: holder
        Layout.fillWidth: true
        spacing: Theme.gap
    }
}
