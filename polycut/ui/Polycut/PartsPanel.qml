import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Polycut

// Parts inspector section (#26): the manual-carve workbench, bound to slice F's
// view-model (`processor.parts`). A tool picker (Cluster / Wand / Brush) with the
// active tool's params, plus the active Part's swatch, inline rename, material slot,
// and add/delete. Carving itself happens by clicking the viewport (the pick slot);
// this panel owns the tool + its settings + the Part table edits. The flat-colour
// "parts" view mode shows the result. (design-system.md §2, §6)
ColumnLayout {
    id: panel
    objectName: "partsPanel"
    Layout.fillWidth: true
    spacing: Theme.sectionGap

    // The simplified mesh's bounding radius (world units) — sizes the brush slider,
    // since the brush reaches in real distance, not topology.
    readonly property real modelRadius: {
        var mn = processor.simplifiedMesh.boundsMin;
        var mx = processor.simplifiedMesh.boundsMax;
        var dx = mx.x - mn.x, dy = mx.y - mn.y, dz = mx.z - mn.z;
        return Math.max(0.001, Math.sqrt(dx * dx + dy * dy + dz * dz) / 2);
    }

    // The active Part's row — recomputed when the rows or the active id move, so the
    // swatch / rename field / slot / delete always reflect the current edit target.
    readonly property var activeRow: {
        var rows = processor.parts.partsRows;
        var id = processor.parts.activePartId;
        for (var i = 0; i < rows.length; i++)
            if (rows[i].id === id) return rows[i];
        return null;
    }
    readonly property bool editingUnassigned: !activeRow || activeRow.id === 0

    function swatch(rgb) { return Qt.rgba(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255, 1); }

    // Seed the brush radius from the model's scale once a cut settles (the brush
    // reaches in world distance; the view-model opens at 0 until QML sizes it).
    Connections {
        target: processor.simplifiedMesh
        function onChanged() {
            if (processor.parts.brushRadius <= 0)
                processor.parts.brushRadius = panel.modelRadius * 0.08;
        }
    }

    Section {
        title: "parts"

        // tool picker — cluster (auto colour-split) / wand (magic colour grow) /
        // brush (spatial paint). Drives `parts.activeTool`; the viewport pick applies it.
        SegmentedToggle {
            Layout.fillWidth: true
            modes: ["cluster", "wand", "brush"]
            current: processor.parts.activeTool
            onSelected: (t) => processor.parts.activeTool = t
        }

        // ---- cluster params: how many colour clusters to split into ----------
        RowLayout {
            visible: processor.parts.activeTool === "cluster"
            Layout.fillWidth: true
            spacing: Theme.gap

            Text {
                text: "clusters"
                color: Theme.fg2
                font.family: Theme.fontUi
                font.pixelSize: Theme.fontSmall
            }
            Item { Layout.fillWidth: true }
            Stepper {
                labels: ["2", "3", "4", "5", "6", "7", "8"]
                currentIndex: processor.parts.clusterK - 2
                onStepped: (d) => processor.parts.clusterK =
                    Math.max(2, Math.min(8, processor.parts.clusterK + d))
                onJumped: (i) => processor.parts.clusterK = i + 2
            }
        }

        // ---- wand params: colour-match threshold + global / local -------------
        ColumnLayout {
            visible: processor.parts.activeTool === "wand"
            Layout.fillWidth: true
            spacing: Theme.gap

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.gap

                Slider {
                    id: thresholdSlider
                    Layout.fillWidth: true
                    from: 0
                    to: 50  // CIELAB ΔE the wand counts as "the same colour"
                    stepSize: 1
                    value: processor.parts.wandThreshold
                    onMoved: processor.parts.wandThreshold = Math.round(value)

                    background: Rectangle {
                        x: thresholdSlider.leftPadding
                        y: thresholdSlider.topPadding + thresholdSlider.availableHeight / 2 - height / 2
                        width: thresholdSlider.availableWidth
                        height: Theme.borderThick * 2
                        radius: height / 2
                        color: Theme.bg2
                        Rectangle {
                            width: thresholdSlider.position * parent.width
                            height: parent.height
                            radius: height / 2
                            color: Theme.teal
                        }
                    }
                    handle: Rectangle {
                        x: thresholdSlider.leftPadding + thresholdSlider.position * (thresholdSlider.availableWidth - width)
                        y: thresholdSlider.topPadding + thresholdSlider.availableHeight / 2 - height / 2
                        implicitWidth: Theme.dotSize + Theme.gapXs
                        implicitHeight: Theme.dotSize + Theme.gapXs
                        radius: width / 2
                        color: thresholdSlider.pressed ? Theme.tealDim : Theme.teal
                    }
                }
                Rectangle {
                    radius: Theme.rSm
                    color: Theme.bg2
                    implicitHeight: Theme.chipHeight
                    implicitWidth: thresholdBadge.implicitWidth + Theme.chipPadH
                    Text {
                        id: thresholdBadge
                        anchors.centerIn: parent
                        text: "ΔE " + Math.round(processor.parts.wandThreshold)
                        color: Theme.teal
                        font.family: Theme.fontMono
                        font.pixelSize: Theme.fontMicro
                    }
                }
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.gap
                Text {
                    text: "match across gaps"
                    color: Theme.fg2
                    font.family: Theme.fontUi
                    font.pixelSize: Theme.fontSmall
                }
                Item { Layout.fillWidth: true }
                Toggle {
                    checked: processor.parts.wandGlobal
                    onToggled: (v) => processor.parts.wandGlobal = v
                }
            }
        }

        // ---- brush params: spatial radius (world units) ----------------------
        RowLayout {
            visible: processor.parts.activeTool === "brush"
            Layout.fillWidth: true
            spacing: Theme.gap

            Slider {
                id: radiusSlider
                Layout.fillWidth: true
                from: 0
                to: panel.modelRadius * 0.5  // up to half the model radius
                value: processor.parts.brushRadius
                onMoved: processor.parts.brushRadius = value

                background: Rectangle {
                    x: radiusSlider.leftPadding
                    y: radiusSlider.topPadding + radiusSlider.availableHeight / 2 - height / 2
                    width: radiusSlider.availableWidth
                    height: Theme.borderThick * 2
                    radius: height / 2
                    color: Theme.bg2
                    Rectangle {
                        width: radiusSlider.position * parent.width
                        height: parent.height
                        radius: height / 2
                        color: Theme.teal
                    }
                }
                handle: Rectangle {
                    x: radiusSlider.leftPadding + radiusSlider.position * (radiusSlider.availableWidth - width)
                    y: radiusSlider.topPadding + radiusSlider.availableHeight / 2 - height / 2
                    implicitWidth: Theme.dotSize + Theme.gapXs
                    implicitHeight: Theme.dotSize + Theme.gapXs
                    radius: width / 2
                    color: radiusSlider.pressed ? Theme.tealDim : Theme.teal
                }
            }
            Rectangle {
                radius: Theme.rSm
                color: Theme.bg2
                implicitHeight: Theme.chipHeight
                implicitWidth: radiusBadge.implicitWidth + Theme.chipPadH
                Text {
                    id: radiusBadge
                    anchors.centerIn: parent
                    text: Number(processor.parts.brushRadius).toLocaleString(Qt.locale("en_US"), 'f', 2)
                    color: Theme.teal
                    font.family: Theme.fontMono
                    font.pixelSize: Theme.fontMicro
                }
            }
        }

        // ---- active Part editor: swatch · inline rename · delete -------------
        RowLayout {
            visible: panel.activeRow !== null
            Layout.fillWidth: true
            spacing: Theme.gap

            Rectangle {  // the active Part's swatch
                implicitWidth: Theme.dotSize + Theme.gapXs
                implicitHeight: Theme.dotSize + Theme.gapXs
                radius: Theme.rSm
                color: panel.activeRow ? panel.swatch(panel.activeRow.colour) : Theme.transparent
                border.color: Theme.hairline
                border.width: Theme.borderThin
            }
            TextField {
                id: nameInput
                Layout.fillWidth: true
                enabled: !panel.editingUnassigned  // the remainder isn't renamed
                color: Theme.fg0
                font.family: Theme.fontUi
                font.pixelSize: Theme.fontBase
                selectByMouse: true
                text: panel.activeRow ? panel.activeRow.name : ""
                onActiveFocusChanged: if (!activeFocus)
                    text = Qt.binding(function () {
                        return panel.activeRow ? panel.activeRow.name : "";
                    })
                onAccepted: {
                    if (!panel.editingUnassigned && text.length > 0)
                        processor.parts.renamePart(processor.parts.activePartId, text);
                    focus = false;
                }
                background: Rectangle {
                    radius: Theme.rMd
                    color: nameInput.enabled ? Theme.bg2 : Theme.transparent
                    border.color: nameInput.activeFocus ? Theme.teal : Theme.hairline
                    border.width: Theme.borderThin
                }
            }
            PillButton {
                text: "delete"
                enabled: !panel.editingUnassigned
                onClicked: processor.parts.deletePart()
            }
        }

        // ---- active Part's material slot (the export → SketchUp mapping) ------
        RowLayout {
            visible: panel.activeRow !== null
            Layout.fillWidth: true
            spacing: Theme.gapXs
            Text {
                text: "slot"
                color: Theme.fg3
                font.family: Theme.fontUi
                font.pixelSize: Theme.fontSmall
            }
            Text {
                text: panel.activeRow ? panel.activeRow.slot : ""
                color: Theme.fg2
                font.family: Theme.fontMono
                font.pixelSize: Theme.fontSmall
                Layout.fillWidth: true
                horizontalAlignment: Text.AlignRight
                elide: Text.ElideLeft
            }
        }

        // ---- add a new Part --------------------------------------------------
        PillButton {
            Layout.fillWidth: true
            text: "+ add part"
            onClicked: processor.parts.createPart()
        }
    }
}
