import QtQuick
import QtQuick.Layouts
import Polycut

// Preserve inspector section (#13): pill toggles for the four attributes the
// texture-preserving collapse can hold onto — UV seams, normals, boundary edges,
// hard edges. Each binds to a bridge view-model flag; flipping one re-runs the cut
// so the before/after preview reflects it. (design-system.md §2, §6)
ColumnLayout {
    id: panel
    Layout.fillWidth: true
    spacing: Theme.sectionGap

    // one labelled pill-toggle row — controlled: binds `value` in, emits `picked` out
    component ToggleRow: RowLayout {
        property alias label: caption.text
        property bool value: false
        signal picked(bool v)

        Layout.fillWidth: true
        spacing: Theme.gap

        Text {
            id: caption
            color: Theme.fg2
            font.family: Theme.fontUi
            font.pixelSize: Theme.fontSmall
        }
        Item { Layout.fillWidth: true }  // push the toggle to the right edge
        Toggle {
            checked: value
            onToggled: (v) => picked(v)
        }
    }

    Section {
        title: "preserve"

        ToggleRow {
            label: "uv seams"
            value: processor.preserveUvSeams
            onPicked: (v) => processor.preserveUvSeams = v
        }
        ToggleRow {
            label: "normals"
            value: processor.preserveNormals
            onPicked: (v) => processor.preserveNormals = v
        }
        ToggleRow {
            label: "boundary edges"
            value: processor.preserveBoundary
            onPicked: (v) => processor.preserveBoundary = v
        }
        ToggleRow {
            label: "hard edges"
            value: processor.preserveHardEdges
            onPicked: (v) => processor.preserveHardEdges = v
        }
    }
}
