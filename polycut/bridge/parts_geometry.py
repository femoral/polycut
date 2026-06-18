"""The QtQuick3D geometry node for the flat-colour Parts view (#26).

Mirror of :class:`~polycut.bridge.mesh_geometry.MeshGeometry`, but for the Parts
workbench: it binds to the :class:`~polycut.bridge.parts_view.PartsViewModel` and
uploads an interleaved position + per-vertex RGBA buffer
(:func:`polycut.core.viewport.build_part_buffers`), so the viewport can draw each
face in its Part's swatch colour with a flat, unlit material. Re-uploads whenever a
carve or a visibility toggle moves the colours. No geometry maths here — only the
GPU wiring — keeping the buffer logic in the headless core seam.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QObject, Signal
from PySide6.QtQml import QmlElement
from PySide6.QtQuick3D import QQuick3DGeometry

QML_IMPORT_NAME = "Polycut.Render"
QML_IMPORT_MAJOR_VERSION = 1

_Semantic = QQuick3DGeometry.Attribute.Semantic
_F32 = QQuick3DGeometry.Attribute.ComponentType.F32Type
_U32 = QQuick3DGeometry.Attribute.ComponentType.U32Type

# Byte offsets into the interleaved vertex (float32: position 3, then RGBA 4).
_POSITION_OFFSET = 0
_COLOR_OFFSET = 12


@QmlElement
class PartsGeometry(QQuick3DGeometry):
    partsModelChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._parts_model = None

    def _get_parts_model(self) -> QObject:
        return self._parts_model

    def _set_parts_model(self, model: QObject) -> None:
        if model is self._parts_model:
            return
        if self._parts_model is not None:
            self._parts_model.geometryChanged.disconnect(self._rebuild)
        self._parts_model = model
        if model is not None:
            model.geometryChanged.connect(self._rebuild)
        self.partsModelChanged.emit()
        self._rebuild()

    partsModel = Property(
        QObject, _get_parts_model, _set_parts_model, notify=partsModelChanged
    )

    def _rebuild(self) -> None:
        """Re-upload the current Parts colour buffer + attribute layout to the GPU."""
        self.clear()
        model = self._parts_model
        if model is None or not model.geometryReady:
            self.update()
            return

        self.setStride(model.geometryStride)
        self.setVertexData(model.geometryVertexData())
        self.setIndexData(model.geometryIndexData())
        self.addAttribute(_Semantic.PositionSemantic, _POSITION_OFFSET, _F32)
        self.addAttribute(_Semantic.ColorSemantic, _COLOR_OFFSET, _F32)
        self.addAttribute(_Semantic.IndexSemantic, 0, _U32)
        self.setPrimitiveType(QQuick3DGeometry.PrimitiveType.Triangles)
        self.setBounds(model.geometryBoundsMin, model.geometryBoundsMax)
        self.update()
