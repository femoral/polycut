import QtQuick
import QtQuick.Layouts
import Polycut

// Stepper — a labeled center value flanked by min / prev / next / max controls
// (design-system.md §6 "Stepper", used for LOD/presets). Controlled like
// SegmentedToggle/Toggle: it holds no state, binds `currentIndex` to a source and
// emits `stepped(direction)` (prev/next, ±1) and `jumped(index)` (min/max ends)
// for the owner to apply. The center shows the matching label, or `customLabel`
// when the index is off-ladder (-1, e.g. the slider landed between presets).
Rectangle {
    id: root

    property var labels: []
    property int currentIndex: -1
    property string customLabel: "Custom"
    signal stepped(int direction)
    signal jumped(int index)

    readonly property int lastIndex: labels.length - 1
    readonly property bool atStart: currentIndex === 0
    readonly property bool atEnd: currentIndex === lastIndex

    implicitHeight: Theme.rowHeight
    implicitWidth: Theme.rowHeight * 6
    radius: height / 2
    color: Theme.bg2
    border.color: Theme.hairline
    border.width: Theme.borderThin

    // one stepper control — a glyph hit-area that dims + goes inert at the end it
    // would step past, so the ladder reads as clamped (no wrap).
    component Control: Item {
        id: ctrl
        property string glyph: ""
        property bool disabled: false
        signal activated()

        Layout.preferredWidth: Theme.rowHeight
        Layout.fillHeight: true

        Text {
            anchors.centerIn: parent
            text: ctrl.glyph
            color: ctrl.disabled ? Theme.fg3 : Theme.fg1  // fg3 = the disabled token
            font.family: Theme.fontUi
            font.pixelSize: Theme.fontBase
        }
        MouseArea {
            anchors.fill: parent
            enabled: !ctrl.disabled
            cursorShape: Qt.PointingHandCursor
            onClicked: ctrl.activated()
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Control {  // min — jump to the least-reduction end (Full)
            glyph: "«"
            disabled: root.atStart
            onActivated: root.jumped(0)
        }
        Control {  // prev — one rung toward less reduction
            glyph: "‹"
            disabled: root.atStart
            onActivated: root.stepped(-1)
        }

        Text {
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignHCenter
            elide: Text.ElideRight
            text: root.currentIndex >= 0 && root.currentIndex < root.labels.length
                ? root.labels[root.currentIndex]
                : root.customLabel
            color: root.currentIndex >= 0 ? Theme.fg0 : Theme.fg2
            font.family: Theme.fontUi
            font.pixelSize: Theme.fontSmall
        }

        Control {  // next — one rung toward more reduction
            glyph: "›"
            disabled: root.atEnd
            onActivated: root.stepped(1)
        }
        Control {  // max — jump to the most-reduction end (Min)
            glyph: "»"
            disabled: root.atEnd
            onActivated: root.jumped(root.lastIndex)
        }
    }
}
