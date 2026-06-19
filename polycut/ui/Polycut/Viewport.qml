import QtQuick
import QtQuick3D
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
    focus: true  // hold keyboard focus so hold-Space (Explode, #31) reaches the handler

    readonly property var original: processor.originalMesh
    readonly property var simplified: processor.simplifiedMesh
    // The after side shows the last good cut; before the first cut lands it falls
    // back to the original so the split is never blank (chip reads "computing…").
    readonly property var afterMesh: simplified && simplified.ready ? simplified : original
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
    // teal line set (the deduped triangle edges — BufferGeometry topology "lines").
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
    // re-uploads (BufferGeometry.update marks the node dirty), but re-decimating at a
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

    // ---- Explode (#31): momentary, view-only spread of the Parts --------
    // Holding Space fans each Part radially out from the model centroid by its chunk
    // offset × amount (Unassigned anchored); the wheel sets amount while held; release
    // re-assembles. Both transitions animate. Never touches the export — this is a
    // pure node-transform spread of cached per-Part chunks, the fused base hidden
    // meanwhile. Holding also force-switches the framing to `simplified` (restored on
    // release); in parts mode it just explodes (the framing toggle is hidden there).
    property bool exploding: false
    property real explodeAmount: 0
    readonly property bool explodeActive: exploding || explodeAmount > 0.0001
    property string _framingBeforeExplode: "split"
    Behavior on explodeAmount {
        NumberAnimation {
            duration: Theme.durStandard
            easing.type: Easing.BezierSpline
            easing.bezierCurve: Theme.easeStandard
        }
    }

    Keys.onPressed: function(event) {
        if (event.key === Qt.Key_Space && !event.isAutoRepeat) {
            if (!root.partsMode) {  // force `simplified` framing for the duration
                root._framingBeforeExplode = root.viewMode;
                root.viewMode = "simplified";
            }
            root.exploding = true;
            root.explodeAmount = 1.0;  // a sensible default — visible at once
            event.accepted = true;
        }
    }
    Keys.onReleased: function(event) {
        if (event.key === Qt.Key_Space && !event.isAutoRepeat) {
            root.exploding = false;
            root.explodeAmount = 0;  // animate the Parts back together
            if (!root.partsMode) root.viewMode = root._framingBeforeExplode;
            event.accepted = true;
        }
    }

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
    // Frame the one shared rig (ADR-0005) head-on: centre the pivot, zero the orbit,
    // dolly back to hold the whole model. The only camera reset — run on a new model
    // and on an up-axis change (#12); otherwise the viewpoint is continuous, including
    // into and out of parts mode (afterCamera + partsCamera mirror this one).
    function _frame() {
        pivot.position = _center();
        pivot.eulerRotation = Qt.vector3d(0, 0, 0);
        camera.z = _radius() * 3.2;  // pull back enough to hold the whole model
    }

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

        // The one shared camera rig (ADR-0005): the input handler orbits `pivot`,
        // pans by moving it, and zooms by dollying `camera.z`. Every render mode draws
        // this viewpoint — afterCamera and the parts camera mirror it — so crossing
        // between modes never resets the view.
        Node {
            id: pivot
            Node {
                // A fixed dolly node the orbit/zoom never writes to. Shifting it by a
                // sub-pixel epsilon on each cut (cutNudge) moves the camera in world
                // space — restarting ProgressiveAA — without the orbit clobbering it.
                x: root.cutNudge
                PerspectiveCamera { id: camera; z: 6; clipNear: 0.01 + root.renderModeNudge }
            }
        }

        Node {  // model node — render-time up-axis rotation (#12), shared by both passes
            pivot: root.modelCenter
            eulerRotation: root.upEuler

            Model {  // the shaded solid; hidden in Wireframe so only the lines show
                visible: root.original && root.original.ready && root.showFill
                geometry: BufferGeometry { source: root.original }
                materials: PrincipledMaterial {
                    baseColor: Theme.fg1
                    baseColorMap: root.textured ? beforeTexture : null
                    roughness: 0.85
                }
            }
            Model {  // edges / wireframe: same vertices, depth-tested against the solid
                visible: root.original && root.original.ready && root.showWire
                depthBias: root.lineDepthBias
                geometry: BufferGeometry { source: root.original; topology: "lines" }
                materials: PrincipledMaterial {
                    // Neutral grey for plain topology — teal is reserved for the
                    // active-Part highlight (#30, design-system §3).
                    baseColor: Theme.fg2
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

                    Model {  // the shaded solid — hidden while the Parts are exploded
                        visible: root.afterMesh && root.afterMesh.ready && root.showFill
                                 && !root.explodeActive
                        geometry: BufferGeometry { source: root.afterMesh }
                        materials: PrincipledMaterial {
                            baseColor: Theme.fg1
                            baseColorMap: root.textured ? afterTexture : null
                            roughness: 0.85
                        }
                    }
                    Model {  // edges / wireframe lines, depth-tested against the solid
                        visible: root.afterMesh && root.afterMesh.ready && root.showWire
                                 && !root.explodeActive
                        depthBias: root.lineDepthBias
                        geometry: BufferGeometry { source: root.afterMesh; topology: "lines" }
                        materials: PrincipledMaterial {
                            baseColor: Theme.fg2  // plain topology grey; teal = highlight
                            lighting: PrincipledMaterial.NoLighting
                        }
                    }
                    // Explode (#31): one node per Part, translated by its cached offset ×
                    // amount, replacing the fused base while Space is held. Each chunk draws
                    // its fill + topology lines so it reads in shaded / edges / wireframe.
                    Repeater3D {
                        model: root.explodeActive ? processor.parts.chunkCount : 0
                        delegate: Node {
                            required property int index
                            position: processor.parts.chunkOffset(index).times(root.explodeAmount)
                            Model {  // chunk fill
                                visible: root.showFill
                                geometry: ExplodeChunkGeometry {
                                    partsModel: processor.parts; chunkIndex: index; topology: "triangles"
                                }
                                materials: PrincipledMaterial {
                                    baseColor: Theme.fg1
                                    baseColorMap: root.textured ? afterTexture : null
                                    roughness: 0.85
                                }
                            }
                            Model {  // chunk edges / wireframe lines
                                visible: root.showWire
                                depthBias: root.lineDepthBias
                                geometry: ExplodeChunkGeometry {
                                    partsModel: processor.parts; chunkIndex: index; topology: "lines"
                                }
                                materials: PrincipledMaterial {
                                    baseColor: Theme.fg2
                                    lighting: PrincipledMaterial.NoLighting
                                }
                            }
                        }
                    }
                }
                Texture { id: afterTexture; source: root.afterMesh ? root.afterMesh.textureUrl : "" }
            }

            // ---- active-Part contour highlight (#30) -------------------
            // An offscreen pass draws just the active Part's faces flat teal on a
            // transparent background; contour.frag edge-detects the projected
            // silhouette and draws a teal ring around it — a topology-independent
            // outline that reads even on the half-disconnected Meshy cut, where an
            // edge-based outline would just be a wireframe. Aligned with afterBase
            // (same camera + size, inside the same clip), so it tracks the after side.
            View3D {
                id: silhouetteView
                anchors.fill: parent
                camera: silhouetteCamera
                environment: SceneEnvironment {
                    backgroundMode: SceneEnvironment.Transparent  // only the Part is opaque
                    antialiasingMode: SceneEnvironment.MSAA  // a crisp, always-current mask
                    antialiasingQuality: SceneEnvironment.High
                }
                PerspectiveCamera {  // mirror the shared camera, like afterCamera
                    id: silhouetteCamera
                    position: camera.scenePosition
                    rotation: camera.sceneRotation
                    fieldOfView: camera.fieldOfView
                    clipNear: camera.clipNear
                }
                Node {  // same render-time up-axis rotation as the after side
                    pivot: root.modelCenter
                    eulerRotation: root.upEuler
                    Model {  // the active Part's faces, flat teal
                        visible: processor.parts.hasHighlight && !root.explodeActive
                        geometry: BufferGeometry { source: processor.parts.highlightSource }
                        materials: PrincipledMaterial {
                            baseColor: Theme.teal
                            lighting: PrincipledMaterial.NoLighting
                        }
                    }
                }
            }
            ShaderEffectSource {  // capture the silhouette as a texture; don't draw it directly
                id: silhouetteSource
                anchors.fill: parent
                sourceItem: silhouetteView
                hideSource: true
                live: true
                visible: false
            }
            ShaderEffect {  // edge-detect the silhouette → teal contour over the after side
                anchors.fill: parent
                visible: processor.parts.hasHighlight && !root.explodeActive
                         && root.afterMesh && root.afterMesh.ready
                property var source: silhouetteSource
                property vector2d texel: Qt.vector2d(width > 0 ? 1.0 / width : 0,
                                                     height > 0 ? 1.0 / height : 0)
                property real thickness: 1.5  // contour reach, in source pixels
                property color outline: Theme.teal
                fragmentShader: "contour.frag.qsb"
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

        // Mirror the one shared camera (ADR-0005): parts draws the same viewpoint as
        // the before/after split, so switching into and out of parts mode never resets
        // the view. partsNudge shifts it a sub-pixel epsilon to restart this view's
        // ProgressiveAA when a carve recolours the buffer — without moving the others.
        PerspectiveCamera {
            id: partsCamera
            position: Qt.vector3d(camera.scenePosition.x + root.partsNudge,
                                  camera.scenePosition.y, camera.scenePosition.z)
            rotation: camera.sceneRotation
            fieldOfView: camera.fieldOfView
            clipNear: camera.clipNear
        }

        Node {  // same render-time up-axis rotation as the before/after passes
            pivot: root.modelCenter
            eulerRotation: root.upEuler

            Model {
                visible: processor.parts.partsSource.ready && !root.explodeActive
                geometry: BufferGeometry { source: processor.parts.partsSource }
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
            // Explode (#31) in the parts render mode: each chunk in its Part's flat
            // swatch colour, translated by its offset × amount, replacing the fused
            // flat-colour mesh while Space is held.
            Repeater3D {
                model: root.explodeActive ? processor.parts.chunkCount : 0
                delegate: Node {
                    required property int index
                    position: processor.parts.chunkOffset(index).times(root.explodeAmount)
                    Model {
                        geometry: ExplodeChunkGeometry {
                            partsModel: processor.parts; chunkIndex: index; topology: "triangles"
                        }
                        materials: PrincipledMaterial {
                            baseColor: {
                                var c = processor.parts.chunkColour(index);
                                return Qt.rgba(c[0] / 255, c[1] / 255, c[2] / 255, 1);
                            }
                            lighting: PrincipledMaterial.NoLighting  // flat swatch, no gradient
                        }
                    }
                }
            }
        }
    }

    // ---- the one viewport input handler (ADR-0005) ---------------------
    // Drives the shared rig in every render mode: right-drag orbits `pivot`, middle
    // pans it, the wheel dollies `camera`. The left button is reserved for the paint
    // tool and is live only in parts mode — click = wand/cluster, drag = brush —
    // handing each stroke's pixel + the shared camera to F's pick slot, which builds
    // the core ray, resolves the face, and applies the active tool. Tools and
    // navigation never share a button, so no second camera rig is needed.
    // NOTE: painting assumes the up-axis is "y" (Meshy's default) — the model node's
    // render-time up rotation is then the identity, so the world ray matches the raw
    // mesh the pick tests. Painting at up = x/z would be misaligned (known follow-up).
    MouseArea {
        id: viewInput
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
        cursorShape: root.partsMode ? Qt.CrossCursor : Qt.ArrowCursor
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
            onTriggered: if (viewInput.strokeDirty) {
                viewInput.strokeDirty = false;
                viewInput.paintAt(viewInput.pendingX, viewInput.pendingY);
            }
        }

        function paintAt(px, py) {
            processor.parts.pick(
                px, py,
                [camera.scenePosition.x, camera.scenePosition.y, camera.scenePosition.z],
                [camera.forward.x, camera.forward.y, camera.forward.z],
                [camera.up.x, camera.up.y, camera.up.z],
                camera.fieldOfView,
                root.width, root.height);
        }

        onPressed: function(mouse) {
            root.forceActiveFocus();  // grab keyboard focus so hold-Space reaches Explode
            lastX = mouse.x;
            lastY = mouse.y;
            // Left paints — but only in parts mode; elsewhere the left button is inert.
            if (mouse.button === Qt.LeftButton && root.partsMode) {
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
            if (painting) {  // brush drag (parts mode, left held): throttle paints the latest
                pendingX = mouse.x;
                pendingY = mouse.y;
                strokeDirty = true;
            } else if (mouse.buttons & Qt.RightButton) {  // orbit
                var e = pivot.eulerRotation;
                pivot.eulerRotation = Qt.vector3d(
                    Math.max(-89, Math.min(89, e.x - dy * 0.3)),  // pitch, clamped
                    e.y - dx * 0.3,                                // yaw
                    0);
            } else if (mouse.buttons & Qt.MiddleButton) {  // pan
                var s = camera.z * 0.0015;
                pivot.position = pivot.position
                    .plus(camera.right.times(-dx * s))
                    .plus(camera.up.times(dy * s));
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

        WheelHandler {  // wheel sets the explode amount while Space is held, else zooms
            acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
            onWheel: function(event) {
                if (root.exploding) {  // adjust the spread, not the dolly
                    root.explodeAmount = Math.max(0, Math.min(4,
                        root.explodeAmount + event.angleDelta.y * 0.0015));
                } else {  // zoom — pull the camera dolly in / out along its view axis
                    camera.z = Math.max(root._radius() * 0.2,
                                        camera.z - event.angleDelta.y * 0.0015 * camera.z);
                }
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

    // ---- one universal processing chip (#29, teal activity, never coral) ----
    // Anchored top-right of the stage, below the "N simplified" caption (which is
    // hidden in parts mode, so they never overlap). Visible in every render mode and
    // framing whenever an op runs — load / simplify / export / cluster — each with its
    // own label off the bridge. The status-bar busy indicator stays the always-on cue.
    Rectangle {
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.rightMargin: Theme.pad
        anchors.topMargin: Theme.pad + Theme.rowHeight  // clear of the face-count caption
        visible: processor.processingLabel !== ""
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
                    running: processor.processingLabel !== ""
                    loops: Animation.Infinite
                    NumberAnimation { from: 1.0; to: 0.3; duration: Theme.durStandard }
                    NumberAnimation { from: 0.3; to: 1.0; duration: Theme.durStandard }
                }
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                // loading… / simplifying… / exporting… / clustering… — the op in flight.
                text: processor.processingLabel
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

    // Re-frame the one shared rig each time a new original (model) arrives.
    Connections {
        target: processor.originalMesh
        function onChanged() { root._frame(); }
    }

    // Re-frame to a head-on front view whenever the up-axis changes, so the re-oriented
    // model is shown framed rather than from the previous orbit (#12).
    Connections {
        target: processor
        function onUpAxisChanged() { root._frame(); }
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
