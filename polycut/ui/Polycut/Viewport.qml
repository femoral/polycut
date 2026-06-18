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
    // Parts is a distinct mode (flat per-Part colour on the simplified mesh), not a
    // shading of the before/after split — so its own full-viewport pass owns the
    // stage and the shaded/wire fills + the before/after chrome stand down.
    readonly property bool partsMode: renderMode === "parts"
    readonly property bool showFill: renderMode === "shaded" || renderMode === "edges"
    readonly property bool showWire: renderMode === "edges" || renderMode === "wireframe"
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
    // The same ProgressiveAA hold bites a fresh cut: the simplified geometry
    // re-uploads (MeshGeometry.update marks the node dirty), but re-decimating at a
    // new target or flipping a Preserve toggle isn't a camera change, so the after
    // side keeps its last converged frame until the next orbit. A projection tweak
    // (clipNear/FOV) doesn't reset the accumulator — only a real camera *transform*
    // change does — so on each cut we shift the camera sideways by a scene-scaled
    // epsilon (~0.05% of the model radius: sub-pixel on screen, but a genuine
    // world-transform delta the after camera mirrors). That restarts both views'
    // AA so the preview reflects the cut at once, without disturbing the orbit. The
    // value alternates back toward zero so it never drifts. (#13 HITL)
    property real cutNudge: 0
    // The same AA-restart trick for the parts view's own camera (see its Connections).
    property real partsNudge: 0

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

    // The parts view has its own independent camera rig (partsPivot + partsCamera),
    // framed on entering parts mode — so parts orbit/pan/zoom never touch the main
    // before/after camera, and switching modes can't corrupt the shaded view.
    function _framePartsCam() {
        partsPivot.position = _center();
        partsPivot.eulerRotation = Qt.vector3d(0, 0, 0);
        partsCamera.position = Qt.vector3d(0, 0, _radius() * 3.2);
    }
    onPartsModeChanged: if (partsMode) _framePartsCam()

    // ---- before side (original, full-res): solid + edge lines ----------
    View3D {
        id: beforeView
        anchors.fill: parent
        visible: root.viewMode !== "simplified" && !root.partsMode

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
            Node {
                // A fixed camera dolly the OrbitCameraController never writes to (it
                // owns `camera`'s own position/rotation). Shifting this by a sub-pixel
                // epsilon on each cut (cutNudge) moves the camera in world space —
                // restarting ProgressiveAA — without the orbit clobbering the nudge.
                x: root.cutNudge
                PerspectiveCamera { id: camera; z: 6; clipNear: 0.01 + root.renderModeNudge }
            }
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
        visible: root.viewMode !== "original" && !root.partsMode
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

    // ---- Parts mode: flat per-Part colour on the simplified mesh --------
    // Its own full-viewport pass, on top of (and replacing) the before/after split.
    // The mesh is the exact simplified geometry the exporter writes; each face is
    // drawn in its Part's swatch colour by an unlit material reading the per-vertex
    // colour buffer, so the swatches read true with no shading gradient. Shares the
    // master camera so orbit/pan/zoom stay in lockstep with the other modes.
    View3D {
        id: partsView
        objectName: "partsView"
        anchors.fill: parent
        visible: root.partsMode

        environment: SceneEnvironment {
            clearColor: Theme.bg0
            backgroundMode: SceneEnvironment.Color
            antialiasingMode: SceneEnvironment.ProgressiveAA
            antialiasingQuality: SceneEnvironment.High
        }

        // Independent camera rig — its own pivot the right-drag orbits, with a nudge
        // node (partsNudge) that shifts it a sub-pixel epsilon to restart ProgressiveAA
        // when a carve recolours the buffer. Never touches the main before/after camera.
        Node {
            id: partsPivot
            Node {
                x: root.partsNudge
                PerspectiveCamera { id: partsCamera; z: 6; clipNear: 0.01 }
            }
        }

        Node {  // same render-time up-axis rotation as the before/after passes
            pivot: root.modelCenter
            eulerRotation: root.upEuler

            Model {
                visible: processor.parts.geometryReady
                geometry: PartsGeometry { partsModel: processor.parts }
                materials: PrincipledMaterial {
                    vertexColorsEnabled: true       // each vertex draws its Part colour
                    baseColor: Theme.white          // identity — the vertex colour shows true
                    lighting: PrincipledMaterial.NoLighting  // flat — no shading gradient
                    // Hidden Parts carry zero vertex alpha; mask (not blend) discards
                    // them outright, so they vanish with no see-through ordering artifacts.
                    alphaMode: PrincipledMaterial.Mask
                    alphaCutoff: 0.5
                }
            }
        }
    }

    // ---- one shared orbit controller drives the before camera -----------
    // Disabled in parts mode, where the left button paints — the parts camera is
    // driven by its own right-orbit / middle-pan / wheel-zoom handler below so tools
    // own the left button and never fight the camera.
    OrbitCameraController {
        anchors.fill: parent
        origin: pivot
        camera: camera
        enabled: !root.partsMode
    }

    // ---- Parts mode input: left paints, right orbits, middle pans, wheel zooms --
    // Active only in parts mode (the OrbitCameraController is disabled there). The
    // left button is the tool — click = wand/cluster, drag = brush — handing each
    // stroke's pixel + camera to F's pick slot, which builds the core ray, resolves
    // the face, and applies the active tool. The right/middle buttons + wheel drive
    // the camera, so tools and navigation never share a button.
    // NOTE: assumes the up-axis is "y" (Meshy's default) — the model node's render-
    // time up rotation is then the identity, so the world ray matches the raw mesh
    // the pick tests. Painting at up = x/z would be misaligned (a known follow-up).
    MouseArea {
        id: partsInput
        anchors.fill: parent
        enabled: root.partsMode
        visible: root.partsMode
        acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
        cursorShape: Qt.CrossCursor
        property bool painting: false
        property real lastX: 0
        property real lastY: 0
        // A brush drag coalesces to the throttle's tick rate: each move only records
        // the latest pointer position, and the timer paints it — so a fast drag can't
        // outrun the per-stamp cost (ray pick + sweep + buffer re-upload) and back up.
        // The prev→current interpolation fills the gaps, so dropping intermediate
        // moves doesn't break the stroke. Click painting stays immediate.
        property real pendingX: 0
        property real pendingY: 0
        property bool strokeDirty: false

        Timer {
            id: paintThrottle
            interval: 24  // ~40 fps stamp cap
            repeat: true
            running: false
            onTriggered: if (partsInput.strokeDirty) {
                partsInput.strokeDirty = false;
                partsInput.paintAt(partsInput.pendingX, partsInput.pendingY);
            }
        }

        function paintAt(px, py) {
            processor.parts.pick(
                px, py,
                [partsCamera.scenePosition.x, partsCamera.scenePosition.y, partsCamera.scenePosition.z],
                [partsCamera.forward.x, partsCamera.forward.y, partsCamera.forward.z],
                [partsCamera.up.x, partsCamera.up.y, partsCamera.up.z],
                partsCamera.fieldOfView,
                root.width, root.height);
        }

        onPressed: function(mouse) {
            lastX = mouse.x;
            lastY = mouse.y;
            if (mouse.button === Qt.LeftButton) {
                processor.parts.beginStroke();  // fresh stroke — don't bridge from the last
                paintAt(mouse.x, mouse.y);
                painting = processor.parts.activeTool === "brush";  // only the brush strokes
                if (painting) {
                    strokeDirty = false;
                    paintThrottle.start();
                }
            }
        }
        onPositionChanged: function(mouse) {
            var dx = mouse.x - lastX, dy = mouse.y - lastY;
            lastX = mouse.x;
            lastY = mouse.y;
            if (mouse.buttons & Qt.LeftButton) {
                if (painting) {  // record latest; the throttle paints it
                    pendingX = mouse.x;
                    pendingY = mouse.y;
                    strokeDirty = true;
                }
            } else if (mouse.buttons & Qt.RightButton) {  // orbit
                var e = partsPivot.eulerRotation;
                partsPivot.eulerRotation = Qt.vector3d(
                    Math.max(-89, Math.min(89, e.x - dy * 0.3)),  // pitch, clamped
                    e.y - dx * 0.3,                                // yaw
                    0);
            } else if (mouse.buttons & Qt.MiddleButton) {  // pan
                var s = partsCamera.z * 0.0015;
                partsPivot.position = partsPivot.position
                    .plus(partsCamera.right.times(-dx * s))
                    .plus(partsCamera.up.times(dy * s));
            }
        }
        onReleased: {
            if (painting) {
                paintThrottle.stop();
                if (strokeDirty) {  // flush the final pointer position
                    strokeDirty = false;
                    paintAt(pendingX, pendingY);
                }
            }
            painting = false;
        }

        WheelHandler {  // zoom — pull the camera dolly in / out along its view axis
            acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
            onWheel: function(event) {
                partsCamera.z = Math.max(root._radius() * 0.2,
                                         partsCamera.z - event.angleDelta.y * 0.0015 * partsCamera.z);
            }
        }
    }

    // ---- divider handle (split mode) -----------------------------------
    Item {
        id: divider
        visible: root.viewMode === "split" && !root.partsMode
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
        visible: root.viewMode !== "simplified" && !root.partsMode
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
        visible: root.viewMode !== "original" && !root.partsMode
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
        visible: processor.simplifying && root.viewMode !== "original" && !root.partsMode
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
        modes: ["shaded", "edges", "wireframe", "parts"]
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
        visible: !root.partsMode  // no before/after concept while painting Parts
        modes: ["original", "split", "simplified"]
        current: root.viewMode
        onSelected: function(mode) { root.viewMode = mode; }
    }

    // Re-frame the camera each time a new original (model) arrives.
    Connections {
        target: processor.originalMesh
        function onChanged() {
            root._frame();
            if (root.partsMode) root._framePartsCam();
        }
    }

    // Reset to a framed front view whenever the up-axis changes, so the re-oriented
    // model is shown head-on rather than from the previous orbit (#12).
    Connections {
        target: processor
        function onUpAxisChanged() { root._resetView(); }
    }

    // Force the after side to repaint when a fresh cut swaps in: shift the camera by
    // a scene-scaled epsilon so ProgressiveAA restarts (see cutNudge). Without this
    // the new geometry — from a slider re-cut or a Preserve toggle — wouldn't show
    // until the next orbit. Alternates back toward zero so the camera never drifts.
    Connections {
        target: processor.simplifiedMesh
        function onChanged() {
            root.cutNudge = root.cutNudge !== 0 ? 0 : root._radius() * 0.0005;
        }
    }

    // A carve recolours the Parts buffer but doesn't move the parts camera, so
    // ProgressiveAA would hold the last frame until the next orbit — the flat-colour
    // view (and so the paint feedback) wouldn't refresh. Nudge the parts camera by a
    // sub-pixel epsilon on every Parts geometry change to restart its accumulator.
    Connections {
        target: processor.parts
        function onGeometryChanged() {
            root.partsNudge = root.partsNudge !== 0 ? 0 : root._radius() * 0.0005;
        }
    }
}
