"""One observable buffer-source the viewport geometry binds to (#32).

The single seam that replaces the per-family scalar plumbing the four geometry
adapters used to read (stride, vertex/index bytes, bounds, ready flags, repeated per
buffer kind). It is **thunk-backed and memoized**: :meth:`bind` arms a builder, and
the first :meth:`current` builds it once and caches the result, so the many property
reads of one rebuild coalesce into a single build — which is why the old per-property
lazy cache disappears.

It serves both feed paths through the same ``current()``/``changed`` interface:

* the **off-thread push** (the heavy mesh): the load/simplify worker pre-builds the
  buffer and calls :meth:`update`, which binds a *pure-return* thunk. A thunk bound
  from a non-GUI thread must already hold its buffer — building thunks run on the GUI
  thread only — so the 646k-vertex interleave never executes on the GUI thread.
* the **on-thread lazy build** (parts / highlight / chunk): the GUI thread binds a
  builder thunk; ``current()`` runs it lazily, on the GUI thread, when QML first reads.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QObject, QUrl, Signal
from PySide6.QtGui import QVector3D


class BufferSource(QObject):
    changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thunk = None
        self._buffers = None
        self._built = False  # whether _buffers holds the memoized current() result
        self._texture_url = QUrl()

    def bind(self, thunk) -> None:
        """Arm a builder ``thunk`` (called at most once per bind), drop the memo, and
        notify. A thunk bound off the GUI thread MUST be a pure return of an
        already-built buffer (see the module docstring's threading invariant)."""
        self._thunk = thunk
        self._buffers = None
        self._built = False
        self.changed.emit()

    def update(self, buffers, texture_url: QUrl = QUrl()) -> None:
        """Adopt a pre-built buffer + texture — the off-thread push path. Binds a
        pure-return thunk, so ``current()`` never builds anything off the GUI thread."""
        self._texture_url = texture_url
        self.bind(lambda: buffers)

    def current(self):
        """The bound buffer, built once and memoized — or ``None`` when nothing is
        bound (or the thunk yields none). One read per rebuild; later reads are free."""
        if not self._built:
            self._buffers = self._thunk() if self._thunk is not None else None
            self._built = True
        return self._buffers

    def _get_ready(self) -> bool:
        return self.current() is not None

    ready = Property(bool, _get_ready, notify=changed)

    def _get_bounds_min(self) -> QVector3D:
        buffers = self.current()
        return QVector3D(*buffers.bounds_min) if buffers else QVector3D()

    boundsMin = Property(QVector3D, _get_bounds_min, notify=changed)

    def _get_bounds_max(self) -> QVector3D:
        buffers = self.current()
        return QVector3D(*buffers.bounds_max) if buffers else QVector3D()

    boundsMax = Property(QVector3D, _get_bounds_max, notify=changed)

    def _get_texture_url(self) -> QUrl:
        return self._texture_url

    textureUrl = Property(QUrl, _get_texture_url, notify=changed)
