import QtQuick
import Polycut

// Single on/off pill toggle — a rounded track (teal when on, bg-3 when off) with a
// thumb that springs across on flip (design-system.md §6 "Pill toggle", §7 spring
// ease). Controlled, like SegmentedToggle: it holds no state, binds `checked` to a
// source and emits `toggled(value)` for the owner to apply.
Rectangle {
    id: root

    property bool checked: false
    signal toggled(bool value)

    readonly property int thumbSize: height - Theme.gapXs
    readonly property int inset: (height - thumbSize) / 2

    implicitHeight: Theme.chipHeight
    implicitWidth: Theme.rowHeight
    radius: height / 2
    color: checked ? Theme.teal : Theme.bg3
    border.color: Theme.hairline
    border.width: Theme.borderThin
    Behavior on color {
        ColorAnimation {
            duration: Theme.durStandard
            easing.type: Easing.BezierSpline
            easing.bezierCurve: Theme.easeSpring
        }
    }

    Rectangle {  // the sliding thumb
        width: root.thumbSize
        height: root.thumbSize
        radius: width / 2
        y: root.inset
        x: root.checked ? root.width - width - root.inset : root.inset
        color: root.checked ? Theme.bg0 : Theme.fg1
        Behavior on x {
            NumberAnimation {
                duration: Theme.durStandard
                easing.type: Easing.BezierSpline
                easing.bezierCurve: Theme.easeSpring
            }
        }
    }

    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: root.toggled(!root.checked)
    }
}
