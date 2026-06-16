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

    // Up-axis remap (#12): the viewport shows the chosen orientation as an instant
    // render-time rotation of the model node — both sides share one euler, so the
    // split stays seamless and y→z→y returns exactly. The export bakes the same
    // rotation in core. Euler matches polycut.core.orient: +Z→+Y is −90° about X,
    // +X→+Y is +90° about Z; "y" is the identity.
    readonly property string upAxis: processor.upAxis
    readonly property vector3d upEuler: upAxis === "z" ? Qt.vector3d(-90, 0, 0)
        : upAxis === "x" ? Qt.vector3d(0, 0, 90)
        : Qt.vector3d(0, 0, 0)
    // Rotate about the model's centre so framing stays put as it turns.
    readonly property vector3d modelCenter: original
        ? Qt.vector3d((original.boundsMin.x + original.boundsMax.x) / 2,
                      (original.boundsMin.y + original.boundsMax.y) / 2,
                      (original.boundsMin.z + original.boundsMax.z) / 2)
        : Qt.vector3d(0, 0, 0)

    // "original" · "split" · "simplified" — the whole-viewport toggle; "split" is
    // the draggable-divider comparison.
    property string viewMode: "split"

    // Shaded · Edges · Wireframe — the render-style toggle (#9). State is owned by
    // the bridge so QML switches rendering off it. Each side's View3D draws the
    // mesh twice in one pass: a shaded solid (the fill) and the same vertices as a
    // teal line set (the deduped triangle edges — MeshGeometry topology "lines").
    // Both share the one depth buffer, so the lines depth-test against the solid:
    // edges behind the surface are occluded instead of leaking through. Shaded =
    // fill only; Edges = fill + lines (topology on the solid); Wireframe = lines
    // only, the fill hidden so every edge shows (density).
    readonly property string renderMode: processor.renderMode
    readonly property bool showFill: renderMode !== "wireframe"  // solid drawn
    readonly property bool showWire: renderMode !== "shaded"     // edge lines drawn
    // The line set lies exactly on the surface, so without a depth nudge it would
    // z-fight the fill (or be culled by the depth test). A small negative bias
    // floats the visible edges just in front of the solid, while edges behind a
    // nearer surface stay far enough back to remain occluded. Tunable by eye (#9).
    readonly property real lineDepthBias: -10
    // Sub-millimetre per-mode nudge to the camera near-plane. ProgressiveAA holds
    // the last converged frame and only restarts on a camera change, so toggling
    // fill / lines alone wouldn't repaint until the next orbit. Folding this into
    // clipNear makes a mode switch count as a camera move → the viewport reflects
    // the new mode at once. Deltas are visually nil (#9).
    readonly property real renderModeNudge: renderMode === "edges" ? 0.0005
        : renderMode === "wireframe" ? 0.001 : 0

    // Outliner selection is reflected in the left panel (row accent) and the status
    // bar — not in the 3D view. A whole-mesh tint can't isolate one object in the
    // fused mesh, and with auto-select it's always on, so it carries no real signal;
    // true per-object viewport highlight needs the MVP-3 Part split (#11 / story 12).

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
    // Reset to the default framed front view — used when the up-axis changes so the
    // re-oriented model is shown head-on instead of from the previous orbit (#12).
    function _resetView() {
        pivot.position = _center();
        camera.position = Qt.vector3d(0, 0, _radius() * 3.2);
        camera.eulerRotation = Qt.vector3d(0, 0, 0);
    }

    // ---- before side (original, full-res): solid + edge lines ----------
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
            PerspectiveCamera { id: camera; z: 6; clipNear: 0.01 + root.renderModeNudge }
        }

        Node {  // model node — render-time up-axis rotation (#12), shared by both passes
            pivot: root.modelCenter
            eulerRotation: root.upEuler

            Model {  // the shaded solid; hidden in Wireframe so only the lines show
                visible: root.original && root.original.hasMesh && root.showFill
                geometry: MeshGeometry { meshView: root.original }
                materials: PrincipledMaterial {
                    baseColor: Theme.fg1
                    baseColorMap: root.textured ? beforeTexture : null
                    roughness: 0.85
                }
            }
            Model {  // edges / wireframe: same vertices, depth-tested against the solid
                visible: root.original && root.original.hasMesh && root.showWire
                depthBias: root.lineDepthBias
                geometry: MeshGeometry { meshView: root.original; topology: "lines" }
                materials: PrincipledMaterial {
                    baseColor: Theme.teal
                    lighting: PrincipledMaterial.NoLighting  // flat lines, not shaded
                }
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

        // Full-viewport size, shifted back so the projection lines up exactly with
        // the before side — only the strip right of the divider is revealed. The
        // last good result stays visible, dimmed, while the next cut runs.
        Item {
            id: afterStage
            width: root.width
            height: root.height
            x: -afterClip.x
            opacity: processor.simplifying ? 0.4 : 1.0
            Behavior on opacity { NumberAnimation { duration: Theme.durStandard } }

            View3D {
                id: afterBase
                anchors.fill: parent

                environment: SceneEnvironment {
                    clearColor: Theme.bg0
                    backgroundMode: SceneEnvironment.Color
                    antialiasingMode: SceneEnvironment.ProgressiveAA
                    antialiasingQuality: SceneEnvironment.High
                }

                DirectionalLight { eulerRotation: Qt.vector3d(-35, -45, 0); brightness: 1.0 }
                DirectionalLight { eulerRotation: Qt.vector3d(25, 130, 0); brightness: 0.45 }

                // Mirror the master camera's world transform — one shared viewpoint.
                PerspectiveCamera {
                    id: afterCamera
                    position: camera.scenePosition
                    rotation: camera.sceneRotation
                    fieldOfView: camera.fieldOfView
                    clipNear: camera.clipNear
                }

                Node {  // model node — same render-time up-axis rotation as the before side
                    pivot: root.modelCenter
                    eulerRotation: root.upEuler

                    Model {  // the shaded solid
                        visible: root.afterMesh && root.afterMesh.hasMesh && root.showFill
                        geometry: MeshGeometry { meshView: root.afterMesh }
                        materials: PrincipledMaterial {
                            baseColor: Theme.fg1
                            baseColorMap: root.textured ? afterTexture : null
                            roughness: 0.85
                        }
                    }
                    Model {  // edges / wireframe lines, depth-tested against the solid
                        visible: root.afterMesh && root.afterMesh.hasMesh && root.showWire
                        depthBias: root.lineDepthBias
                        geometry: MeshGeometry { meshView: root.afterMesh; topology: "lines" }
                        materials: PrincipledMaterial {
                            baseColor: Theme.teal
                            lighting: PrincipledMaterial.NoLighting
                        }
                    }
                }
                Texture { id: afterTexture; source: root.afterMesh ? root.afterMesh.textureUrl : "" }
            }
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

    // ---- render-style toggle: shaded · wireframe · edges (#9) ----------
    // Top of the viewport, per the prototype: how the geometry is drawn. State
    // lives in the bridge; this only reflects + sets it.
    SegmentedToggle {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: parent.top
        anchors.topMargin: Theme.pad
        z: 10
        modes: ["shaded", "edges", "wireframe"]
        current: root.renderMode
        onSelected: function(mode) { processor.renderMode = mode; }
    }

    // ---- whole-viewport toggle: original · split · simplified ----------
    // Bottom: which model fills the stage / the draggable comparison.
    SegmentedToggle {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: Theme.pad
        z: 10
        modes: ["original", "split", "simplified"]
        current: root.viewMode
        onSelected: function(mode) { root.viewMode = mode; }
    }

    // Re-frame the camera each time a new original (model) arrives.
    Connections {
        target: processor.originalMesh
        function onChanged() { root._frame(); }
    }

    // Reset to a framed front view whenever the up-axis changes, so the re-oriented
    // model is shown head-on rather than from the previous orbit (#12).
    Connections {
        target: processor
        function onUpAxisChanged() { root._resetView(); }
    }
}
