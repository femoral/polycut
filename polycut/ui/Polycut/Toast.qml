import QtQuick
import QtQuick.Layouts
import Polycut

// Transient bottom notification for results (post-export), auto-dismiss.
// (design-system.md §6)
Rectangle {
    id: root
    property string message: ""
    property string actionText: ""
    property bool mono: false  // true for numeric readouts (post-export summary)
    signal actionTriggered()

    function show(msg, action, useMono) {
        message = msg;
        actionText = action === undefined ? "" : action;
        mono = useMono === true;
        visible = true;
        opacity = 1;
        hideTimer.restart();
    }

    radius: Theme.rMd
    color: Theme.bg2
    border.color: Theme.hairline
    border.width: Theme.borderThin
    visible: false
    opacity: 0
    implicitHeight: Theme.rowHeight + Theme.gap
    implicitWidth: row.implicitWidth + 2 * Theme.pad
    Behavior on opacity {
        NumberAnimation {
            duration: Theme.durStandard
            easing.type: Easing.BezierSpline
            easing.bezierCurve: Theme.easeStandard
        }
    }
    onOpacityChanged: if (opacity === 0) visible = false

    RowLayout {
        id: row
        anchors.centerIn: parent
        spacing: Theme.gap

        Text {
            text: root.message
            color: Theme.fg1
            font.family: root.mono ? Theme.fontMono : Theme.fontUi
            font.pixelSize: Theme.fontBase
        }

        PillButton {
            visible: root.actionText !== ""
            text: root.actionText
            onClicked: root.actionTriggered()
        }
    }

    Timer { id: hideTimer; interval: 6000; onTriggered: root.opacity = 0 }
}
