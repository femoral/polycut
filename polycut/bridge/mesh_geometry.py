"""The QtQuick3D geometry node the viewport renders (#8).

A ``QQuick3DGeometry`` that mirrors the bridge's :class:`MeshView`: it binds to
``processor.meshData`` and, on every change, re-uploads the interleaved vertex
buffer + triangle index buffer with the fixed position/normal/UV attribute
layout :func:`polycut.core.build_mesh_buffers` emits. Registered as a QML type so
``Viewport.qml`` can hand it to a ``Model``. No geometry maths lives here — only
the GPU wiring — keeping the buffer logic in the headless core seam.
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
class MeshGeometry(QQuick3DGeometry):
    meshViewChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._mesh_view = None

    def _get_mesh_view(self) -> QObject:
        return self._mesh_view

    def _set_mesh_view(self, view: QObject) -> None:
        if view is self._mesh_view:
            return
        if self._mesh_view is not None:
            self._mesh_view.changed.disconnect(self._rebuild)
        self._mesh_view = view
        if view is not None:
            view.changed.connect(self._rebuild)
        self.meshViewChanged.emit()
        self._rebuild()

    meshView = Property(
        QObject, _get_mesh_view, _set_mesh_view, notify=meshViewChanged
    )

    def _rebuild(self) -> None:
        """Re-upload the current mesh's buffers + attribute layout to the GPU."""
        self.clear()
        view = self._mesh_view
        if view is None or not view.hasMesh:
            self.update()
            return

        self.setStride(view.stride)
        self.setVertexData(view.vertexData())
        self.setIndexData(view.indexData())
        self.addAttribute(_Semantic.PositionSemantic, _POSITION_OFFSET, _F32)
        self.addAttribute(_Semantic.NormalSemantic, _NORMAL_OFFSET, _F32)
        self.addAttribute(_Semantic.TexCoordSemantic, _UV_OFFSET, _F32)
        self.addAttribute(_Semantic.IndexSemantic, 0, _U32)
        self.setPrimitiveType(QQuick3DGeometry.PrimitiveType.Triangles)
        self.setBounds(view.boundsMin, view.boundsMax)
        self.update()
