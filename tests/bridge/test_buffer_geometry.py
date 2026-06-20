"""The one generic geometry seam: BufferSource + BufferGeometry (#32).

Four near-identical ``QQuick3DGeometry`` adapters (mesh / parts / highlight / chunk)
ran the same upload dance and differed only in attribute layout and which view-model
signal they bound. They collapse onto one layout-driven ``BufferGeometry`` reading one
observable ``BufferSource``. These pin the adapter's GPU configuration and the
source's thunk/memoisation behaviour headless (no window); the pixels stay HITL.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh
from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtQuick3D import QQuick3DGeometry

from polycut.bridge.buffer_geometry import BufferGeometry
from polycut.bridge.buffer_source import BufferSource
from polycut.core import build_mesh_buffers
from polycut.core.model import SourceModel

_Primitive = QQuick3DGeometry.PrimitiveType


def _quad_buffers():
    """A 2-triangle textured quad's mesh buffers (pos/normal/uv, with edges)."""
    mesh = trimesh.Trimesh(
        vertices=np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=float),
        faces=np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64),
        vertex_normals=np.tile([0.0, 0.0, 1.0], (4, 1)),
        visual=trimesh.visual.TextureVisuals(
            uv=np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=float)
        ),
        process=False,
    )
    model = SourceModel(Path("quad.obj"), mesh, 2, 1, ())
    return build_mesh_buffers(model)


class _FakeSource(QObject):
    """A minimal stand-in for BufferSource: a ``changed`` signal and a ``current()``
    returning whatever buffer it was handed — so the adapter is tested in isolation."""

    changed = Signal()

    def __init__(self, buffers=None):
        super().__init__()
        self._buffers = buffers

    def current(self):
        return self._buffers

    def set(self, buffers):
        self._buffers = buffers
        self.changed.emit()


def test_adapter_uploads_a_bound_sources_buffer(qapp):
    """Binding a source configures the stride, attributes, primitive type and the
    uploaded vertex/index bytes from the buffer the source yields."""
    buffers = _quad_buffers()
    geom = BufferGeometry()
    geom.source = _FakeSource(buffers)

    assert geom.stride() == 32  # pos(12) + normal(12) + uv(8)
    assert geom.attributeCount() == 4  # position, normal, texcoord, index
    assert geom.primitiveType() == _Primitive.Triangles
    assert bytes(geom.vertexData()) == buffers.vertex_data
    assert bytes(geom.indexData()) == buffers.index_data


def test_adapter_clears_when_the_source_yields_none(qapp):
    """A source with no buffer (nothing bound) leaves the geometry empty — no
    attributes, no stale upload."""
    geom = BufferGeometry()
    geom.source = _FakeSource(None)

    assert geom.attributeCount() == 0
    assert bytes(geom.vertexData()) == b""


def test_topology_lines_swaps_to_the_edge_index_and_line_primitive(qapp):
    """In 'lines' topology the adapter uploads the buffer's edge index buffer as a
    Lines primitive, while keeping the same vertex buffer the solid uses — so the
    Edges / Wireframe pass depth-tests against the fill."""
    buffers = _quad_buffers()
    geom = BufferGeometry()
    geom.source = _FakeSource(buffers)
    assert geom.primitiveType() == _Primitive.Triangles

    geom.topology = "lines"

    assert geom.primitiveType() == _Primitive.Lines
    assert bytes(geom.indexData()) == buffers.line_index_data
    assert bytes(geom.vertexData()) == buffers.vertex_data  # shared verts


def test_adapter_re_uploads_when_the_source_changes(qapp):
    """When the bound source emits ``changed`` with a new buffer, the geometry
    re-uploads — the viewport stays live across a re-cut / re-arm."""
    source = _FakeSource(_quad_buffers())
    geom = BufferGeometry()
    geom.source = source
    before = bytes(geom.indexData())

    triangle = trimesh.Trimesh(
        vertices=np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float),
        faces=np.array([[0, 1, 2]], dtype=np.int64),
        vertex_normals=np.tile([0.0, 0.0, 1.0], (3, 1)),
        process=False,
    )
    source.set(build_mesh_buffers(SourceModel(Path("t.obj"), triangle, 1, 1, ())))

    assert bytes(geom.indexData()) != before


def test_source_builds_its_thunk_once_and_memoizes(qapp):
    """The source builds its thunk at most once per bind — the many property reads of
    one rebuild (ready, bounds, the adapter's current()) coalesce into a single build,
    which is why the old per-property lazy cache is gone."""
    buffers = _quad_buffers()
    calls = {"n": 0}

    def thunk():
        calls["n"] += 1
        return buffers

    source = BufferSource()
    source.bind(thunk)
    source.current()
    source.current()
    _ = source.ready
    _ = source.boundsMin

    assert calls["n"] == 1


def test_source_rearms_on_rebind(qapp):
    """Re-binding (the carve / selection invalidation) drops the memo, so the next
    ``current()`` builds the freshly-armed thunk instead of the stale cache."""
    source = BufferSource()
    source.bind(lambda: _quad_buffers())
    first = source.current()

    other = _quad_buffers()
    source.bind(lambda: other)

    assert source.current() is other
    assert source.current() is not first


def test_update_adopts_a_prebuilt_buffer_and_texture(qapp):
    """The off-thread push path: ``update`` adopts an already-built buffer (a pure
    return, never built on the GUI thread) plus its texture URL."""
    buffers = _quad_buffers()
    url = QUrl.fromLocalFile("/tmp/baked.png")

    source = BufferSource()
    source.update(buffers, url)

    assert source.ready is True
    assert source.current() is buffers
    assert source.textureUrl == url
