"""The mesh + texture the Qt3D viewport draws, surfaced to QML (#8).

A thin, observable view-model: the bridge fills it with the current geometry's
render buffers (built off-thread by :func:`polycut.core.build_mesh_buffers`) and
the baked texture URL, then emits :attr:`changed`. The QML ``QQuick3DGeometry``
binds to it and re-uploads on change. No geometry logic lives here — only
exposure — so the buffer maths stays in the headless core seam.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QByteArray, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QVector3D


class MeshView(QObject):
    changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._buffers = None
        self._texture_url = QUrl()

    def update(self, buffers, texture_url: QUrl) -> None:
        """Adopt new render buffers + texture and notify QML. Called off-thread."""
        self._buffers = buffers
        self._texture_url = texture_url
        self.changed.emit()

    def _get_has_mesh(self) -> bool:
        return self._buffers is not None

    hasMesh = Property(bool, _get_has_mesh, notify=changed)

    def _get_vertex_count(self) -> int:
        return self._buffers.vertex_count if self._buffers else 0

    vertexCount = Property(int, _get_vertex_count, notify=changed)

    def _get_triangle_count(self) -> int:
        return self._buffers.triangle_count if self._buffers else 0

    triangleCount = Property(int, _get_triangle_count, notify=changed)

    def _get_texture_url(self) -> QUrl:
        return self._texture_url

    textureUrl = Property(QUrl, _get_texture_url, notify=changed)

    def _get_stride(self) -> int:
        return self._buffers.stride if self._buffers else 0

    stride = Property(int, _get_stride, notify=changed)

    def _get_bounds_min(self) -> QVector3D:
        return QVector3D(*self._buffers.bounds_min) if self._buffers else QVector3D()

    boundsMin = Property(QVector3D, _get_bounds_min, notify=changed)

    def _get_bounds_max(self) -> QVector3D:
        return QVector3D(*self._buffers.bounds_max) if self._buffers else QVector3D()

    boundsMax = Property(QVector3D, _get_bounds_max, notify=changed)

    @Slot(result=QByteArray)
    def vertexData(self) -> QByteArray:
        """The interleaved vertex buffer the geometry uploads (empty when none)."""
        return QByteArray(self._buffers.vertex_data) if self._buffers else QByteArray()

    @Slot(result=QByteArray)
    def indexData(self) -> QByteArray:
        """The triangle index buffer the geometry uploads (empty when none)."""
        return QByteArray(self._buffers.index_data) if self._buffers else QByteArray()
