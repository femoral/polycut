"""The QtQuick3D geometry node for one explode chunk (#31).

A per-Part slice of the simplified mesh, drawn as its own translated node while
Space is held. It binds to the :class:`~polycut.bridge.parts_view.PartsViewModel`
and a ``chunkIndex`` and uploads that chunk's interleaved position/normal/UV buffer
(:func:`polycut.core.viewport.build_part_chunks`) with either the triangle indices
(the shaded / flat fill) or the unique-edge indices (edges / wireframe) — the same
dual-topology trick :class:`~polycut.bridge.mesh_geometry.MeshGeometry` uses, so a
chunk shades and textures exactly like the assembled mesh in every render mode. A
``Repeater3D`` instantiates one per chunk; only the node transform changes as the
explode amount moves, never the buffers.
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

# Byte offsets into the interleaved vertex (float32: position 3, normal 3, uv 2).
_POSITION_OFFSET = 0
_NORMAL_OFFSET = 12
_UV_OFFSET = 24


@QmlElement
class ExplodeChunkGeometry(QQuick3DGeometry):
    partsModelChanged = Signal()
    chunkIndexChanged = Signal()
    topologyChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._parts_model = None
        self._chunk_index = -1
        self._topology = "triangles"  # "triangles" (fill) | "lines" (edges / wireframe)

    def _get_parts_model(self) -> QObject:
        return self._parts_model

    def _set_parts_model(self, model: QObject) -> None:
        if model is self._parts_model:
            return
        if self._parts_model is not None:
            self._parts_model.geometryChanged.disconnect(self._rebuild)
        self._parts_model = model
        if model is not None:
            model.geometryChanged.connect(self._rebuild)  # chunks rebuilt on a carve
        self.partsModelChanged.emit()
        self._rebuild()

    partsModel = Property(
        QObject, _get_parts_model, _set_parts_model, notify=partsModelChanged
    )

    def _get_chunk_index(self) -> int:
        return self._chunk_index

    def _set_chunk_index(self, value: int) -> None:
        value = int(value)
        if value == self._chunk_index:
            return
        self._chunk_index = value
        self.chunkIndexChanged.emit()
        self._rebuild()

    chunkIndex = Property(int, _get_chunk_index, _set_chunk_index, notify=chunkIndexChanged)

    def _get_topology(self) -> str:
        return self._topology

    def _set_topology(self, value: str) -> None:
        if value not in ("triangles", "lines") or value == self._topology:
            return
        self._topology = value
        self.topologyChanged.emit()
        self._rebuild()

    topology = Property(str, _get_topology, _set_topology, notify=topologyChanged)

    def _rebuild(self) -> None:
        """Re-upload the bound chunk's buffers + attribute layout to the GPU."""
        self.clear()
        model = self._parts_model
        index = self._chunk_index
        if model is None or not 0 <= index < model.chunkCount:
            self.update()
            return

        lines = self._topology == "lines"
        self.setStride(model.chunkStride(index))
        self.setVertexData(model.chunkVertexData(index))
        self.setIndexData(
            model.chunkLineData(index) if lines else model.chunkTriangleData(index)
        )
        self.addAttribute(_Semantic.PositionSemantic, _POSITION_OFFSET, _F32)
        self.addAttribute(_Semantic.NormalSemantic, _NORMAL_OFFSET, _F32)
        self.addAttribute(_Semantic.TexCoordSemantic, _UV_OFFSET, _F32)
        self.addAttribute(_Semantic.IndexSemantic, 0, _U32)
        self.setPrimitiveType(
            QQuick3DGeometry.PrimitiveType.Lines
            if lines
            else QQuick3DGeometry.PrimitiveType.Triangles
        )
        self.setBounds(model.chunkBoundsMin(index), model.chunkBoundsMax(index))
        self.update()
