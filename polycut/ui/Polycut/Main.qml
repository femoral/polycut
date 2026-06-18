import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Dialogs
import Polycut

ApplicationWindow {
    id: win
    visible: true
    width: 1180
    height: 760
    minimumWidth: 920
    minimumHeight: 600
    title: "Polycut"
    color: Theme.bg0

    property bool dragging: false
    property string lastOutputPath: ""

    function fmt(n) { return Number(n).toLocaleString(Qt.locale("en_US"), 'f', 0); }
    function fmtSize(bytes) {
        if (bytes >= 1048576) return (bytes / 1048576).toFixed(1) + " MB";
        if (bytes >= 1024) return (bytes / 1024).toFixed(0) + " KB";
        return bytes + " B";
    }

    // ---- result wiring -------------------------------------------------
    Connections {
        target: processor
        function onExportFinished(path, sizeBytes, faceCount, textureCount) {
            win.lastOutputPath = path;
            toast.show(
                fmtSize(sizeBytes) + " · " + fmt(faceCount) + " faces · " +
                textureCount + " texture" + (textureCount === 1 ? "" : "s"),
                "Reveal in Explorer", true);
        }
        function onExportFailed(message) { toast.show("Export failed: " + message); }
        function onLoadFailed(message) { toast.show("Could not load: " + message); }
    }

    FileDialog {
        id: openDialog
        title: "Open a Meshy model"
        nameFilters: ["Wavefront OBJ (*.obj)"]
        onAccepted: processor.loadFile(selectedFile)
    }
    FileDialog {
        id: saveDialog
        title: "Export to SketchUp"
        fileMode: FileDialog.SaveFile
        defaultSuffix: "dae"
        nameFilters: ["Collada (*.dae)"]
        onAccepted: processor.exportModel(selectedFile)
    }

    // ---- shell ---------------------------------------------------------
    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // Top bar: identity + version (left) · filename + format (center) · breadcrumb (right)
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 48
            color: Theme.bg1
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Theme.pad
                anchors.rightMargin: Theme.pad
                spacing: Theme.gap

                Text {
                    text: "Polycut"
                    color: Theme.fg0
                    font.family: Theme.fontUi
                    font.pixelSize: Theme.fontLg
                    font.bold: true
                }
                Rectangle {
                    radius: Theme.rSm
                    color: Theme.bg2
                    implicitHeight: Theme.chipHeight
                    implicitWidth: ver.implicitWidth + Theme.chipPadH
                    Text {
                        id: ver
                        anchors.centerIn: parent
                        text: "v0.1.0"
                        color: Theme.fg2
                        font.family: Theme.fontMono
                        font.pixelSize: Theme.fontMicro
                    }
                }

                Item { Layout.fillWidth: true }

                Text {
                    text: processor.hasModel ? processor.fileName : "no model loaded"
                    color: processor.hasModel ? Theme.fg1 : Theme.fg3
                    font.family: Theme.fontUi
                    font.pixelSize: Theme.fontBase
                }
                Rectangle {
                    visible: processor.hasModel
                    radius: Theme.rSm
                    color: Theme.bg2
                    implicitHeight: Theme.chipHeight
                    implicitWidth: fmtTag.implicitWidth + Theme.chipPadH
                    Text {
                        id: fmtTag
                        anchors.centerIn: parent
                        text: "OBJ"
                        color: Theme.teal
                        font.family: Theme.fontMono
                        font.pixelSize: Theme.fontMicro
                    }
                }

                Item { Layout.fillWidth: true }

                // process breadcrumb — steps that exist today: IMPORT → SIMPLIFY → EXPORT
                RowLayout {
                    spacing: Theme.gapXs
                    Repeater {
                        model: ["IMPORT", "SIMPLIFY", "EXPORT"]
                        delegate: RowLayout {
                            required property int index
                            required property string modelData
                            spacing: Theme.gapXs
                            Text {
                                text: modelData
                                font.family: Theme.fontMono
                                font.pixelSize: Theme.fontMicro
                                font.letterSpacing: Theme.headerSpacing
                                color: {
                                    var step = processor.hasModel ? 1 : 0;  // loaded → at SIMPLIFY
                                    return index === step ? Theme.teal : Theme.fg3;
                                }
                            }
                            Text {
                                visible: index < 2
                                text: "→"
                                color: Theme.fg3
                                font.pixelSize: Theme.fontMicro
                            }
                        }
                    }
                }
            }
            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: Theme.borderThin; color: Theme.hairline }
        }

        // Body: outliner · center stage · inspector
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            // Scene Outliner
            Rectangle {
                Layout.fillHeight: true
                implicitWidth: 240
                color: Theme.bg1
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: Theme.pad
                    spacing: Theme.gap

                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            text: "PARTS"
                            color: Theme.fg2
                            font.family: Theme.fontUi
                            font.pixelSize: Theme.fontSmall
                            font.letterSpacing: Theme.headerSpacing
                            font.bold: true
                        }
                        Item { Layout.fillWidth: true }
                        Text {
                            // running total = the partitioned (simplified) mesh, which the
                            // per-Part counts sum to exactly; the live cut is the hero stat.
                            text: processor.hasModel ? win.fmt(processor.parts.totalFaceCount) : "0"
                            color: Theme.fg1
                            font.family: Theme.fontMono
                            font.pixelSize: Theme.fontSmall
                        }
                    }

                    // Part rows — one per Part (incl. the Unassigned remainder), bound to
                    // the view-model (#26). List-row pattern (§6): colour swatch + name +
                    // right-aligned mono face count + a visibility (eye) toggle; the active
                    // edit target gets the teal left-accent + bg-2. Selecting a row makes it
                    // active (drives the viewport highlight + where tool strokes land).
                    ListView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        visible: processor.hasModel
                        clip: true
                        spacing: Theme.gapXs
                        model: processor.parts.partsRows
                        boundsBehavior: Flickable.StopAtBounds
                        delegate: Rectangle {
                            required property int index
                            required property var modelData
                            width: ListView.view.width
                            implicitHeight: Theme.rowHeight
                            radius: Theme.rSm
                            readonly property bool selected: modelData.id === processor.parts.activePartId
                            color: selected ? Theme.bg2 : Theme.transparent
                            Rectangle {  // teal left-accent on the active row
                                width: Theme.borderThick
                                height: parent.height
                                radius: Theme.borderThin
                                color: Theme.teal
                                visible: parent.selected
                            }
                            MouseArea {  // row select — under the eye toggle, which sits on top
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: processor.parts.activePartId = modelData.id
                            }
                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: Theme.gap
                                anchors.rightMargin: Theme.gap
                                spacing: Theme.gapXs
                                Rectangle {  // colour swatch (dims when hidden)
                                    implicitWidth: Theme.dotSize + Theme.gapXs
                                    implicitHeight: Theme.dotSize + Theme.gapXs
                                    radius: Theme.rSm
                                    color: Qt.rgba(modelData.colour[0] / 255,
                                                   modelData.colour[1] / 255,
                                                   modelData.colour[2] / 255, 1)
                                    border.color: Theme.hairline
                                    border.width: Theme.borderThin
                                    opacity: modelData.visible ? 1.0 : 0.35
                                }
                                Text {
                                    text: modelData.name
                                    color: modelData.visible ? Theme.fg0 : Theme.fg3
                                    font.family: Theme.fontUi
                                    font.pixelSize: Theme.fontBase
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                                Text {
                                    text: win.fmt(modelData.faceCount)
                                    color: Theme.fg2
                                    font.family: Theme.fontMono
                                    font.pixelSize: Theme.fontSmall
                                }
                                Text {  // eye toggle — show / hide the Part in the flat-colour view
                                    text: modelData.visible ? "◉" : "○"
                                    color: modelData.visible ? Theme.fg2 : Theme.fg3
                                    font.family: Theme.fontUi
                                    font.pixelSize: Theme.fontBase
                                    MouseArea {
                                        anchors.fill: parent
                                        anchors.margins: -Theme.gapXs  // easier hit target
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: processor.parts.setPartVisible(
                                            modelData.id, !modelData.visible)
                                    }
                                }
                            }
                        }
                    }

                    Text {
                        visible: !processor.hasModel
                        text: "no parts yet"
                        color: Theme.fg3
                        font.family: Theme.fontUi
                        font.pixelSize: Theme.fontSmall
                    }

                    Item { visible: !processor.hasModel; Layout.fillHeight: true }
                }
                Rectangle { anchors.right: parent.right; height: parent.height; width: Theme.borderThin; color: Theme.hairline }
            }

            // Center stage
            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true

                EmptyState {
                    anchors.fill: parent
                    visible: !processor.hasModel
                    dragActive: win.dragging
                    showSample: typeof sampleModelPath !== "undefined" && sampleModelPath !== ""
                    onBrowse: openDialog.open()
                    onLoadSample: processor.loadFile(sampleModelPath)
                }

                // The live 3D viewport (MVP-2) — shaded, textured render of the
                // current cut, orbit/pan/zoom. Replaces the MVP-1 empty canvas.
                Viewport {
                    anchors.fill: parent
                    visible: processor.hasModel
                }

                // The DropArea keeps the stage a working drop target (load /
                // replace a model) over both the empty state and the viewport.
                DropArea {
                    anchors.fill: parent
                    onEntered: (drag) => { if (drag.hasUrls) win.dragging = true; }
                    onExited: win.dragging = false
                    onDropped: (drop) => {
                        win.dragging = false;
                        if (drop.hasUrls) processor.loadFile(drop.urls[0]);
                    }
                }
            }

            // Right inspector
            Rectangle {
                Layout.fillHeight: true
                implicitWidth: 300
                color: Theme.bg1
                Rectangle { anchors.left: parent.left; height: parent.height; width: Theme.borderThin; color: Theme.hairline }

                ScrollView {
                    anchors.fill: parent
                    anchors.margins: Theme.pad
                    clip: true
                    contentWidth: availableWidth

                    ColumnLayout {
                        width: parent.width
                        spacing: Theme.sectionGap

                        Text {
                            visible: !processor.hasModel
                            text: "load a model to see its stats"
                            color: Theme.fg3
                            font.family: Theme.fontUi
                            font.pixelSize: Theme.fontSmall
                        }

                        // Simplify — hero delta + reduction slider + target input.
                        SimplifyPanel {
                            visible: processor.hasModel
                            Layout.fillWidth: true
                        }

                        // Preserve — pill toggles steering what the collapse keeps.
                        PreservePanel {
                            visible: processor.hasModel
                            Layout.fillWidth: true
                        }

                        // Transform — scale multiplier + source/target units.
                        TransformPanel {
                            visible: processor.hasModel
                            Layout.fillWidth: true
                        }

                        // Texture status — warning shown inline (§7), coral when missing.
                        RowLayout {
                            visible: processor.hasModel
                            Layout.fillWidth: true
                            spacing: Theme.gap
                            Rectangle {
                                implicitWidth: Theme.dotSize
                                implicitHeight: Theme.dotSize
                                radius: width / 2
                                color: processor.hasTexture ? Theme.teal : Theme.coral
                            }
                            Text {
                                text: processor.hasTexture
                                    ? processor.textureName
                                    : "no texture found — export will be untextured"
                                color: processor.hasTexture ? Theme.fg1 : Theme.coral
                                font.family: processor.hasTexture ? Theme.fontMono : Theme.fontUi
                                font.pixelSize: Theme.fontSmall
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                        }

                        // Parts — manual carve workbench: tool picker + params +
                        // the active Part's swatch / rename / slot / add-delete. The
                        // flat-colour "parts" view mode shows the result. (#26)
                        // Sits after Transform until a Materials section ships; at that
                        // point Materials takes the canonical §2 slot and Parts moves
                        // below it (tracked with the inspector reorg, see #26 discussion).
                        PartsPanel {
                            visible: processor.hasModel
                            Layout.fillWidth: true
                        }
                    }
                }
            }
        }

        // Status bar: state (left) · primary action (far right)
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 42
            color: Theme.bg1
            Rectangle { anchors.top: parent.top; width: parent.width; height: Theme.borderThin; color: Theme.hairline }
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Theme.pad
                anchors.rightMargin: Theme.pad
                spacing: Theme.gap

                BusyIndicator {
                    running: processor.busy
                    visible: processor.busy
                    implicitWidth: Theme.iconSm
                    implicitHeight: Theme.iconSm
                }
                Text {
                    text: processor.status
                    color: Theme.fg2
                    font.family: Theme.fontUi
                    font.pixelSize: Theme.fontSmall
                }
                Text {  // selection narration (§7): the active Part edit target
                    visible: processor.hasModel
                    text: {
                        var rows = processor.parts.partsRows;
                        var id = processor.parts.activePartId;
                        for (var i = 0; i < rows.length; i++)
                            if (rows[i].id === id) return "· active: " + rows[i].name;
                        return "";
                    }
                    color: Theme.fg3
                    font.family: Theme.fontUi
                    font.pixelSize: Theme.fontSmall
                }
                Item { Layout.fillWidth: true }
                // Open another model without restarting — drag-drop already
                // replaces the model, this makes it discoverable. Secondary so
                // Export stays the one primary action. (design-system.md §6)
                PillButton {
                    text: "Open another"
                    visible: processor.hasModel
                    enabled: !processor.busy
                    onClicked: openDialog.open()
                }
                PillButton {
                    text: "Export to SketchUp"
                    primary: true
                    enabled: processor.hasModel && !processor.busy
                    onClicked: {
                        saveDialog.currentFile = processor.defaultExportPath;
                        saveDialog.open();
                    }
                }
            }
        }
    }

    // Post-export toast
    Toast {
        id: toast
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: Theme.rowHeight + Theme.pad  // clears the status bar
        onActionTriggered: processor.revealInExplorer(win.lastOutputPath)
    }
}
