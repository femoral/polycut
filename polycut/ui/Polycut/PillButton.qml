import QtQuick
import QtQuick.Controls.Basic
import Polycut

// Buttons — primary: filled teal, bg-0 text (once per context); secondary:
// bg-2 fill, fg-1 text. (design-system.md §6)
Button {
    id: control
    property bool primary: false

    implicitHeight: Theme.rowHeight
    leftPadding: Theme.pad
    rightPadding: Theme.pad
    font.family: Theme.fontUi
    font.pixelSize: Theme.fontBase

    contentItem: Text {
        text: control.text
        font: control.font
        color: control.primary ? Theme.bg0 : Theme.fg1
        opacity: control.enabled ? 1.0 : 0.5
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }

    background: Rectangle {
        radius: Theme.rMd
        color: control.primary
            ? (control.down ? Theme.tealDim : Theme.teal)
            : (control.down ? Theme.bg3 : Theme.bg2)
        border.color: control.primary ? "transparent" : Theme.hairline
        border.width: control.primary ? 0 : Theme.borderThin
        opacity: control.enabled ? 1.0 : 0.5
        Behavior on color {
            ColorAnimation {
                duration: Theme.durFast
                easing.type: Easing.BezierSpline
                easing.bezierCurve: Theme.easeStandard
            }
        }
    }
}
