import QtQuick
import Polycut

// Segmented pill toggle — one rounded bg-2 track with a teal thumb that springs
// to the active segment (design-system.md §6 "Pill toggle", §7 spring ease), not
// a row of loose buttons. Generic over a list of string modes; emits `selected`
// when a segment is tapped. Drives the viewport's render-mode (top) and
// before/after (bottom) switches — one switch widget, two uses.
Rectangle {
    id: root

    property var modes: []
    property string current: ""
    signal selected(string mode)

    readonly property int activeIndex: modes.indexOf(current)
    // Equal-width segments; segW grows to the widest label so the thumb slides
    // cleanly across uniform cells. Seeded at the row height as a sane floor.
    property real segW: Theme.rowHeight

    implicitHeight: Theme.rowHeight
    implicitWidth: segW * modes.length + Theme.borderThick * 2
    radius: height / 2
    color: Theme.bg2
    border.color: Theme.hairline
    border.width: Theme.borderThin

    Rectangle {  // the active-segment thumb
        width: root.segW
        height: parent.height - Theme.borderThick * 2
        y: Theme.borderThick
        x: Theme.borderThick + Math.max(0, root.activeIndex) * root.segW
        radius: height / 2
        color: Theme.teal
        visible: root.activeIndex >= 0
        Behavior on x {
            NumberAnimation {
                duration: Theme.durStandard
                easing.type: Easing.BezierSpline
                easing.bezierCurve: Theme.easeSpring
            }
        }
    }

    Row {
        x: Theme.borderThick
        anchors.verticalCenter: parent.verticalCenter
        spacing: 0
        Repeater {
            model: root.modes
            delegate: Item {
                required property string modelData
                readonly property bool active: root.current === modelData
                width: root.segW
                height: root.height
                Text {
                    anchors.centerIn: parent
                    text: modelData
                    color: parent.active ? Theme.bg0 : Theme.fg1
                    font.family: Theme.fontUi
                    font.pixelSize: Theme.fontSmall
                    // Push the widest label up to segW so every cell fits its text.
                    onImplicitWidthChanged: root.segW = Math.max(root.segW, implicitWidth + Theme.pad * 2)
                }
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.selected(modelData)
                }
            }
        }
    }
}
