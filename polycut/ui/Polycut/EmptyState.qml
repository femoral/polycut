import QtQuick
import QtQuick.Layouts
import Polycut

// Center-stage empty state: large rounded dropzone with icon, headline, format
// chips, Browse (primary) + Load sample (secondary). (design-system.md §6)
Item {
    id: root
    signal browse()
    signal loadSample()
    property bool dragActive: false
    property bool showSample: false

    Rectangle {
        anchors.centerIn: parent
        width: Math.min(parent.width - 2 * Theme.pad, 520)
        height: col.implicitHeight + Theme.sectionGap * 4
        radius: Theme.rLg
        color: root.dragActive ? Qt.rgba(Theme.teal.r, Theme.teal.g, Theme.teal.b, 0.06) : Theme.transparent
        border.color: root.dragActive ? Theme.teal : Theme.bg3
        border.width: root.dragActive ? Theme.borderThick : Theme.borderThin
        Behavior on border.color {
            ColorAnimation {
                duration: Theme.durFast
                easing.type: Easing.BezierSpline
                easing.bezierCurve: Theme.easeStandard
            }
        }

        ColumnLayout {
            id: col
            anchors.centerIn: parent
            width: parent.width - 2 * Theme.pad
            spacing: Theme.sectionGap

            Text {
                Layout.alignment: Qt.AlignHCenter
                text: "⬇"
                color: Theme.teal
                font.pixelSize: Theme.iconLg
            }

            Text {
                Layout.alignment: Qt.AlignHCenter
                text: "Drop your model to begin"
                color: Theme.fg0
                font.family: Theme.fontUi
                font.pixelSize: Theme.fontHeadline
            }

            Text {
                Layout.alignment: Qt.AlignHCenter
                text: "bring textures along too"
                color: Theme.fg2
                font.family: Theme.fontUi
                font.pixelSize: Theme.fontSmall
            }

            RowLayout {
                Layout.alignment: Qt.AlignHCenter
                spacing: Theme.gap
                Repeater {
                    model: ["GLB", "GLTF", "DAE", "OBJ", "PLY", "STL", "OFF"]
                    delegate: Rectangle {
                        required property string modelData
                        radius: Theme.rSm
                        color: Theme.bg2
                        implicitHeight: Theme.chipHeight
                        implicitWidth: chip.implicitWidth + Theme.chipPadH
                        Text {
                            id: chip
                            anchors.centerIn: parent
                            text: parent.modelData
                            color: Theme.fg2
                            font.family: Theme.fontMono
                            font.pixelSize: Theme.fontSmall
                        }
                    }
                }
            }

            RowLayout {
                Layout.alignment: Qt.AlignHCenter
                Layout.topMargin: Theme.gap
                spacing: Theme.gap
                PillButton {
                    text: "Browse files"
                    primary: true
                    onClicked: root.browse()
                }
                PillButton {
                    visible: root.showSample
                    text: "Load sample"
                    onClicked: root.loadSample()
                }
            }
        }
    }
}
