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
                            text: "SCENE OUTLINER"
                            color: Theme.fg2
                            font.family: Theme.fontUi
                            font.pixelSize: Theme.fontSmall
                            font.letterSpacing: Theme.headerSpacing
                            font.bold: true
                        }
                        Item { Layout.fillWidth: true }
                        Text {
                            text: processor.hasModel ? win.fmt(processor.faceCount) : "0"
                            color: Theme.fg1
                            font.family: Theme.fontMono
                            font.pixelSize: Theme.fontSmall
                        }
                    }

                    // object rows (one fused mesh in MVP-1)
                    Rectangle {
                        visible: processor.hasModel
                        Layout.fillWidth: true
                        implicitHeight: Theme.rowHeight
                        radius: Theme.rSm
                        color: Theme.bg2
                        Rectangle { width: Theme.borderThick; height: parent.height; color: Theme.teal; radius: Theme.borderThin }
                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: Theme.gap
                            anchors.rightMargin: Theme.gap
                            Text {
                                text: "model"
                                color: Theme.fg0
                                font.family: Theme.fontUi
                                font.pixelSize: Theme.fontBase
                            }
                            Item { Layout.fillWidth: true }
                            Text {
                                text: win.fmt(processor.faceCount)
                                color: Theme.fg2
                                font.family: Theme.fontMono
                                font.pixelSize: Theme.fontSmall
                            }
                        }
                    }

                    Text {
                        visible: !processor.hasModel
                        text: "no objects yet"
                        color: Theme.fg3
                        font.family: Theme.fontUi
                        font.pixelSize: Theme.fontSmall
                    }

                    Item { Layout.fillHeight: true }
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

                // Once a model is loaded the centre is an empty canvas — the
                // live 3D viewport ships in MVP-2. The DropArea below keeps it a
                // working drop target (load / replace a model); no placeholder.

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
                Item { Layout.fillWidth: true }
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
