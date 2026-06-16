import QtQuick
import QtQuick3D
import QtQuick3D.Helpers
import Polycut
import Polycut.Render

// The center-stage before/after split (#10): the original (full-res) Source model
// on the left, the simplified result on the right, with a draggable divider and a
// whole-viewport original / split / simplified toggle. Both sides share one camera
// (the after camera mirrors the before camera's scene transform) so orbit / pan /
// zoom move them in lockstep. Render is decoupled from the cut (ADR-0003): the
// original draws immediately while the after side computes async — dimmed, with a
// teal "simplifying…" chip, until the fresh cut swaps in. The simplified mesh is
// the exact geometry the exporter writes, never a preview-only cut.
Item {
    id: root
    objectName: "viewport"

    readonly property var original: processor.originalMesh
    readonly property var simplified: processor.simplifiedMesh
    // The after side shows the last good cut; before the first cut lands it falls
    // back to the original so the split is never blank (chip reads "computing…").
    readonly property var afterMesh: simplified && simplified.hasMesh ? simplified : original
    readonly property bool textured: original && original.textureUrl.toString() !== ""

    // "original" · "split" · "simplified" — the whole-viewport toggle; "split" is
    // the draggable-divider comparison.
    property string viewMode: "split"

    function _center() {
        return Qt.vector3d(
            (original.boundsMin.x + original.boundsMax.x) / 2,
            (original.boundsMin.y + original.boundsMax.y) / 2,
            (original.boundsMin.z + original.boundsMax.z) / 2);
    }
    function _radius() {
        var dx = original.boundsMax.x - original.boundsMin.x;
        var dy = original.boundsMax.y - original.boundsMin.y;
        var dz = original.boundsMax.z - original.boundsMin.z;
        return Math.max(0.001, Math.sqrt(dx * dx + dy * dy + dz * dz) / 2);
    }
    function _frame() {
        pivot.position = _center();
        camera.z = _radius() * 3.2;  // pull back enough to hold the whole model
    }

    // ---- before side (original, full-res) ------------------------------
    View3D {
        id: beforeView
        anchors.fill: parent
        visible: root.viewMode !== "simplified"

        environment: SceneEnvironment {
            clearColor: Theme.bg0  // the dark-neutral stage — content is the focus
            backgroundMode: SceneEnvironment.Color
            // ProgressiveAA, not MSAA: one sample while the camera moves (keeps
            // orbit/zoom at full frame rate), accumulating to a crisp image once
            // it settles — MSAA paid its multisample cost every frame.
            antialiasingMode: SceneEnvironment.ProgressiveAA
            antialiasingQuality: SceneEnvironment.High
        }

        DirectionalLight { eulerRotation: Qt.vector3d(-35, -45, 0); brightness: 1.0 }
        DirectionalLight { eulerRotation: Qt.vector3d(25, 130, 0); brightness: 0.45 }

        Node {
            id: pivot
            PerspectiveCamera { id: camera; z: 6; clipNear: 0.01 }
        }

        Model {
            visible: root.original && root.original.hasMesh
            geometry: MeshGeometry { meshView: root.original }
            materials: PrincipledMaterial {
                baseColor: Theme.fg1
                baseColorMap: root.textured ? beforeTexture : null
                roughness: 0.85
            }
        }
        Texture { id: beforeTexture; source: root.original ? root.original.textureUrl : "" }
    }

    // ---- after side (simplified) — clipped to the right of the divider --
    Item {
        id: afterClip
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        // split: from the divider rightward; simplified: whole viewport.
        x: root.viewMode === "split" ? divider.x : 0
        width: root.width - x
        visible: root.viewMode !== "original"
        clip: true

        View3D {
            id: afterView
            // Full-viewport size, shifted back so its projection lines up exactly
            // with the before side — only the divider strip is revealed.
            width: root.width
            height: root.height
            x: -afterClip.x
            // The last good result stays visible, dimmed, while the next cut runs.
            opacity: processor.simplifying ? 0.4 : 1.0
            Behavior on opacity { NumberAnimation { duration: Theme.durStandard } }

            environment: SceneEnvironment {
                clearColor: Theme.bg0
                backgroundMode: SceneEnvironment.Color
                antialiasingMode: SceneEnvironment.ProgressiveAA
                antialiasingQuality: SceneEnvironment.High
            }

            DirectionalLight { eulerRotation: Qt.vector3d(-35, -45, 0); brightness: 1.0 }
            DirectionalLight { eulerRotation: Qt.vector3d(25, 130, 0); brightness: 0.45 }

            // Mirror the before camera's world transform — one shared viewpoint.
            PerspectiveCamera {
                id: afterCamera
                position: camera.scenePosition
                rotation: camera.sceneRotation
                fieldOfView: camera.fieldOfView
                clipNear: camera.clipNear
            }

            Model {
                visible: root.afterMesh && root.afterMesh.hasMesh
                geometry: MeshGeometry { meshView: root.afterMesh }
                materials: PrincipledMaterial {
                    baseColor: Theme.fg1
                    baseColorMap: root.textured ? afterTexture : null
                    roughness: 0.85
                }
            }
            Texture { id: afterTexture; source: root.afterMesh ? root.afterMesh.textureUrl : "" }
        }
    }

    // ---- one shared orbit controller drives the before camera -----------
    OrbitCameraController {
        anchors.fill: parent
        origin: pivot
        camera: camera
    }

    // ---- divider handle (split mode) -----------------------------------
    Item {
        id: divider
        visible: root.viewMode === "split"
        x: root.width / 2
        y: 0
        width: Theme.gap
        height: root.height

        Rectangle {  // the seam line
            anchors.horizontalCenter: parent.horizontalCenter
            width: Theme.borderThick
            height: parent.height
            color: Theme.teal
            opacity: 0.85
        }
        Rectangle {  // grab handle
            anchors.centerIn: parent
            width: Theme.iconSm + Theme.gapXs
            height: Theme.rowHeight
            radius: Theme.rSm
            color: dividerDrag.containsPress ? Theme.tealDim : Theme.bg2
            border.color: Theme.teal
            border.width: Theme.borderThin
            Text {
                anchors.centerIn: parent
                text: "‹ ›"
                color: Theme.teal
                font.family: Theme.fontUi
                font.pixelSize: Theme.fontSmall
            }
        }
        MouseArea {
            id: dividerDrag
            anchors.fill: parent
            anchors.margins: -Theme.gap  // generous grab target
            cursorShape: Qt.SizeHorCursor
            drag.target: divider
            drag.axis: Drag.XAxis
            drag.minimumX: Theme.pad
            drag.maximumX: root.width - Theme.pad
        }
    }

    // ---- side captions: name + mono face count -------------------------
    Row {
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.margins: Theme.pad
        spacing: Theme.gapXs
        visible: root.viewMode !== "simplified"
        Text {
            text: "original"
            color: Theme.fg2
            font.family: Theme.fontUi
            font.pixelSize: Theme.fontSmall
        }
        Text {
            text: Number(processor.originalFaceCount).toLocaleString(Qt.locale("en_US"), 'f', 0)
            color: Theme.fg0
            font.family: Theme.fontMono
            font.pixelSize: Theme.fontSmall
        }
    }
    Row {
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: Theme.pad
        spacing: Theme.gapXs
        visible: root.viewMode !== "original"
        Text {
            text: Number(processor.faceCount).toLocaleString(Qt.locale("en_US"), 'f', 0)
            color: Theme.fg0
            font.family: Theme.fontMono
            font.pixelSize: Theme.fontSmall
        }
        Text {
            text: "simplified"
            color: Theme.fg2
            font.family: Theme.fontUi
            font.pixelSize: Theme.fontSmall
        }
    }

    // ---- in-progress chip (teal activity, never coral) -----------------
    Rectangle {
        anchors.horizontalCenter: afterClip.horizontalCenter
        anchors.top: parent.top
        anchors.topMargin: Theme.pad + Theme.rowHeight
        visible: processor.simplifying && root.viewMode !== "original"
        implicitHeight: Theme.chipHeight + Theme.gapXs
        implicitWidth: chipRow.implicitWidth + Theme.chipPadH * 2
        radius: height / 2
        color: Theme.bg2
        border.color: Theme.teal
        border.width: Theme.borderThin

        Row {
            id: chipRow
            anchors.centerIn: parent
            spacing: Theme.gapXs
            Rectangle {  // pulsing activity dot
                anchors.verticalCenter: parent.verticalCenter
                width: Theme.dotSize; height: Theme.dotSize; radius: width / 2
                color: Theme.teal
                SequentialAnimation on opacity {
                    running: processor.simplifying
                    loops: Animation.Infinite
                    NumberAnimation { from: 1.0; to: 0.3; duration: Theme.durStandard }
                    NumberAnimation { from: 0.3; to: 1.0; duration: Theme.durStandard }
                }
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                // First load has no prior cut → "computing first cut…"; later cuts
                // keep the last good mesh dimmed → "simplifying…".
                text: root.simplified && root.simplified.hasMesh ? "simplifying…" : "computing first cut…"
                color: Theme.teal
                font.family: Theme.fontUi
                font.pixelSize: Theme.fontSmall
            }
        }
    }

    // ---- whole-viewport toggle: original · split · simplified ----------
    // One rounded pill track with a teal thumb that springs to the active
    // segment (design-system.md §6 "Pill toggle"), not three loose buttons.
    Rectangle {
        id: modeToggle
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: Theme.pad
        z: 10

        readonly property var modes: ["original", "split", "simplified"]
        readonly property int activeIndex: modes.indexOf(root.viewMode)
        // Equal-width segments (sized to the widest label) so the thumb slides cleanly.
        readonly property real segW: segMetrics.width + Theme.pad * 2

        implicitHeight: Theme.rowHeight
        implicitWidth: segW * modes.length + Theme.borderThick * 2
        radius: height / 2
        color: Theme.bg2
        border.color: Theme.hairline
        border.width: Theme.borderThin

        TextMetrics {
            id: segMetrics
            font.family: Theme.fontUi
            font.pixelSize: Theme.fontSmall
            text: "simplified"
        }

        Rectangle {  // the active-segment thumb
            width: modeToggle.segW
            height: parent.height - Theme.borderThick * 2
            y: Theme.borderThick
            x: Theme.borderThick + modeToggle.activeIndex * modeToggle.segW
            radius: height / 2
            color: Theme.teal
            Behavior on x {
                NumberAnimation {  // spring ease — playful affordance (§5)
                    duration: Theme.durStandard
                    easing.type: Easing.BezierSpline
                    easing.bezierCurve: [0.34, 1.4, 0.64, 1.0, 1.0, 1.0]
                }
            }
        }

        Row {
            x: Theme.borderThick
            anchors.verticalCenter: parent.verticalCenter
            spacing: 0
            Repeater {
                model: modeToggle.modes
                delegate: Item {
                    required property string modelData
                    readonly property bool active: root.viewMode === modelData
                    width: modeToggle.segW
                    height: modeToggle.height
                    Text {
                        anchors.centerIn: parent
                        text: modelData
                        color: parent.active ? Theme.bg0 : Theme.fg1
                        font.family: Theme.fontUi
                        font.pixelSize: Theme.fontSmall
                    }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.viewMode = modelData
                    }
                }
            }
        }
    }

    // Re-frame the camera each time a new original (model) arrives.
    Connections {
        target: processor.originalMesh
        function onChanged() { root._frame(); }
    }
}
