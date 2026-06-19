"""The QtQuick3D geometry node for the active-Part highlight silhouette (#30).

Mirror of :class:`~polycut.bridge.parts_geometry.PartsGeometry`: it binds to the
:class:`~polycut.bridge.parts_view.PartsViewModel` and uploads the active Part's
**faces** — a position-only vertex buffer (the fused mesh's own vertices) plus the
Part's triangle indices (:func:`polycut.core.viewport.build_highlight_buffers`).
``Viewport.qml`` draws it flat into an offscreen mask whose screen-space edge becomes
a teal contour around the projected Part — a topology-independent outline that reads
even on the half-disconnected Meshy cut. Re-uploads whenever the highlight moves (a
carve or a selection change); empty when Unassigned is the edit target. No geometry
maths here — only the GPU wiring.
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

_POSITION_OFFSET = 0  # position-only vertices (3 × float32)


@QmlElement
class HighlightGeometry(QQuick3DGeometry):
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
            self._parts_model.highlightChanged.disconnect(self._rebuild)
        self._parts_model = model
        if model is not None:
            model.highlightChanged.connect(self._rebuild)
        self.partsModelChanged.emit()
        self._rebuild()

    partsModel = Property(
        QObject, _get_parts_model, _set_parts_model, notify=partsModelChanged
    )

    def _rebuild(self) -> None:
        """Re-upload the active Part's faces to the GPU as a Triangles primitive — the
        silhouette the offscreen mask pass draws."""
        self.clear()
        model = self._parts_model
        if model is None or not model.highlightReady:
            self.update()
            return

        self.setStride(model.highlightStride)
        self.setVertexData(model.highlightVertexData())
        self.setIndexData(model.highlightIndexData())
        self.addAttribute(_Semantic.PositionSemantic, _POSITION_OFFSET, _F32)
        self.addAttribute(_Semantic.IndexSemantic, 0, _U32)
        self.setPrimitiveType(QQuick3DGeometry.PrimitiveType.Triangles)
        self.setBounds(model.highlightBoundsMin, model.highlightBoundsMax)
        self.update()
