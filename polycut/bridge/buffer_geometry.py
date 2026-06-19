"""One layout-driven geometry adapter for the whole viewport (#32).

Replaces the four near-identical ``QQuick3DGeometry`` subclasses (mesh / parts /
highlight / chunk) that each ran the same upload dance and differed only in their
hardcoded attribute offsets. ``BufferGeometry`` binds one :class:`BufferSource`,
reads the buffer once via :meth:`BufferSource.current`, and uploads by **looping the
buffer's own layout** — no per-kind subclass, no offsets written out here. The only
Qt-specific knowledge is one small, stable map from the core's neutral attribute
vocabulary to Qt3D's semantics; it never changes when the core interleave changes.

The triangles/lines topology toggle (the solid vs. the Edges/Wireframe line pass)
stays on the adapter, sharing the buffer's one vertex data across both index buffers.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QByteArray, QObject, Signal
from PySide6.QtGui import QVector3D
from PySide6.QtQml import QmlElement
from PySide6.QtQuick3D import QQuick3DGeometry

from polycut.core.viewport import Attr

QML_IMPORT_NAME = "Polycut.Render"
QML_IMPORT_MAJOR_VERSION = 1

_Semantic = QQuick3DGeometry.Attribute.Semantic
_F32 = QQuick3DGeometry.Attribute.ComponentType.F32Type
_U32 = QQuick3DGeometry.Attribute.ComponentType.U32Type

# The one map from the core's Qt-free attribute kinds to Qt3D semantics. Stable: it
# never changes when the core interleave (the offsets) changes — only this enumeration
# of which kinds exist would, and it covers them all.
_SEMANTIC = {
    Attr.POSITION: _Semantic.PositionSemantic,
    Attr.NORMAL: _Semantic.NormalSemantic,
    Attr.TEXCOORD: _Semantic.TexCoordSemantic,
    Attr.COLOR: _Semantic.ColorSemantic,
}


@QmlElement
class BufferGeometry(QQuick3DGeometry):
    sourceChanged = Signal()
    topologyChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._source = None
        self._topology = "triangles"  # "triangles" (solid / fill) | "lines" (edges / wire)

    def _get_source(self) -> QObject:
        return self._source

    def _set_source(self, source: QObject) -> None:
        if source is self._source:
            return
        if self._source is not None:
            self._source.changed.disconnect(self._rebuild)
        self._source = source
        if source is not None:
            source.changed.connect(self._rebuild)
        self.sourceChanged.emit()
        self._rebuild()

    source = Property(QObject, _get_source, _set_source, notify=sourceChanged)

    def _get_topology(self) -> str:
        return self._topology

    def _set_topology(self, value: str) -> None:
        if value not in ("triangles", "lines") or value == self._topology:
            return
        self._topology = value
        self.topologyChanged.emit()
        self._rebuild()  # swap the index buffer + primitive type

    topology = Property(str, _get_topology, _set_topology, notify=topologyChanged)

    def _rebuild(self) -> None:
        """Re-upload the bound buffer + its declared attribute layout to the GPU.

        One ``current()`` read, one none-guard, and the attributes added by looping the
        layout — so the same adapter serves every buffer kind. Both topologies share the
        one vertex buffer; only the index buffer and primitive type differ.
        """
        self.clear()
        source = self._source
        buffers = source.current() if source is not None else None
        if buffers is None:
            self.update()
            return

        lines = self._topology == "lines"
        self.setStride(buffers.stride)
        self.setVertexData(QByteArray(buffers.vertex_data))
        self.setIndexData(
            QByteArray(buffers.line_index_data if lines else buffers.index_data)
        )
        for attr in buffers.layout:
            self.addAttribute(_SEMANTIC[attr.kind], attr.offset, _F32)
        self.addAttribute(_Semantic.IndexSemantic, 0, _U32)
        self.setPrimitiveType(
            QQuick3DGeometry.PrimitiveType.Lines
            if lines
            else QQuick3DGeometry.PrimitiveType.Triangles
        )
        self.setBounds(QVector3D(*buffers.bounds_min), QVector3D(*buffers.bounds_max))
        self.update()
