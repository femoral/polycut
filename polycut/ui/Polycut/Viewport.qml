import QtQuick
import QtQuick3D
import QtQuick3D.Helpers
import Polycut
import Polycut.Render

// The center-stage 3D viewport (#8): renders the bridge's current mesh shaded
// with its baked texture, on the dark-neutral stage (design-system.md §1). Orbit
// / pan / zoom come from OrbitCameraController. The mesh + texture arrive via
// processor.meshData — the same faithful geometry the exporter writes (ADR-0003).
Item {
    id: root
    objectName: "viewport"

    readonly property var mesh: processor.meshData
    readonly property bool textured: mesh && mesh.textureUrl.toString() !== ""

    function _center() {
        return Qt.vector3d(
            (mesh.boundsMin.x + mesh.boundsMax.x) / 2,
            (mesh.boundsMin.y + mesh.boundsMax.y) / 2,
            (mesh.boundsMin.z + mesh.boundsMax.z) / 2);
    }
    function _radius() {
        var dx = mesh.boundsMax.x - mesh.boundsMin.x;
        var dy = mesh.boundsMax.y - mesh.boundsMin.y;
        var dz = mesh.boundsMax.z - mesh.boundsMin.z;
        return Math.max(0.001, Math.sqrt(dx * dx + dy * dy + dz * dz) / 2);
    }
    function _frame() {
        pivot.position = _center();
        camera.z = _radius() * 3.2;  // pull back enough to hold the whole model
    }

    View3D {
        id: view
        anchors.fill: parent

        environment: SceneEnvironment {
            clearColor: Theme.bg0  // the dark-neutral stage — content is the focus
            backgroundMode: SceneEnvironment.Color
            // ProgressiveAA, not MSAA: render one sample while the camera moves
            // (cheap — keeps orbit/zoom at full frame rate) and accumulate to a
            // crisp image once it settles. MSAA paid its full multisample cost
            // every frame, which was fill-rate-bound and dropped FPS on orbit.
            antialiasingMode: SceneEnvironment.ProgressiveAA
            antialiasingQuality: SceneEnvironment.High
        }

        // Key + fill so the shaded form reads without a texture too.
        DirectionalLight { eulerRotation: Qt.vector3d(-35, -45, 0); brightness: 1.0 }
        DirectionalLight { eulerRotation: Qt.vector3d(25, 130, 0); brightness: 0.45 }

        Node {
            id: pivot
            PerspectiveCamera {
                id: camera
                z: 6
                clipNear: 0.01
            }
        }

        Model {
            id: meshModel
            visible: root.mesh && root.mesh.hasMesh
            geometry: MeshGeometry { meshView: root.mesh }
            materials: PrincipledMaterial {
                baseColor: Theme.fg1
                baseColorMap: root.textured ? bakedTexture : null
                roughness: 0.85
            }
        }

        Texture {
            id: bakedTexture
            source: root.mesh ? root.mesh.textureUrl : ""
        }
    }

    OrbitCameraController {
        anchors.fill: parent
        origin: pivot
        camera: camera
    }

    // Re-frame the camera each time a new cut (or model) arrives.
    Connections {
        target: processor.meshData
        function onChanged() { root._frame(); }
    }
}
