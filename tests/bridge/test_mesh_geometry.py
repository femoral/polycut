"""The QtQuick3D geometry the viewport draws, fed from the bridge view-model (#8).

``MeshGeometry`` is a ``QQuick3DGeometry`` the QML ``Model`` uses for its mesh.
It binds to ``processor.simplifiedMesh`` and, whenever that changes, re-uploads the
interleaved vertex buffer + index buffer with the position/normal/UV attribute
layout the core builder emits. Constructing it headless (no window) lets us pin
that GPU configuration here; the shaded pixels themselves are HITL (#15).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import trimesh

from polycut.bridge.mesh_geometry import MeshGeometry
from polycut.bridge.mesh_view import MeshView
from polycut.core import build_mesh_buffers
from polycut.core.model import SourceModel


@pytest.fixture
def quad_view():
    """A MeshView pre-filled with a 2-triangle quad's render buffers."""
    mesh = trimesh.Trimesh(
        vertices=np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=float),
        faces=np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64),
        vertex_normals=np.tile([0.0, 0.0, 1.0], (4, 1)),
        visual=trimesh.visual.TextureVisuals(
            uv=np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=float)
        ),
        process=False,
    )
    model = SourceModel(
        source_path=Path("quad.obj"),
        geometry=mesh,
        face_count=2,
        object_count=1,
        texture_path=None,
    )
    from PySide6.QtCore import QUrl

    view = MeshView()
    view.update(build_mesh_buffers(model), QUrl())
    return view


def test_geometry_uploads_buffers_and_attributes(qapp, quad_view):
    """Binding a loaded meshView configures the stride, attributes, and buffers."""
    geometry = MeshGeometry()
    geometry.meshView = quad_view

    assert geometry.stride() == 32  # pos(12) + normal(12) + uv(8)
    assert geometry.attributeCount() == 4  # position, normal, texcoord, index
    assert bytes(geometry.vertexData()) == bytes(quad_view.vertexData())
    assert bytes(geometry.indexData()) == bytes(quad_view.indexData())


def test_geometry_re_uploads_when_the_mesh_changes(qapp, quad_view):
    """A re-cut (meshView.changed) re-uploads the buffers — the viewport stays live."""
    from PySide6.QtCore import QUrl

    geometry = MeshGeometry()
    geometry.meshView = quad_view
    before = bytes(geometry.indexData())

    triangle = SourceModel(
        source_path=Path("tri.obj"),
        geometry=trimesh.Trimesh(
            vertices=np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float),
            faces=np.array([[0, 1, 2]], dtype=np.int64),
            vertex_normals=np.tile([0.0, 0.0, 1.0], (3, 1)),
            process=False,
        ),
        face_count=1,
        object_count=1,
        texture_path=None,
    )
    quad_view.update(build_mesh_buffers(triangle), QUrl())  # fires changed

    assert bytes(geometry.indexData()) != before
    assert bytes(geometry.indexData()) == bytes(quad_view.indexData())


def test_lines_topology_uploads_edges_as_a_line_primitive(qapp, quad_view):
    """In 'lines' topology the geometry draws the deduped triangle edges as a line
    primitive (the Wireframe / Edges modes), sharing the solid's vertex buffer so
    it can be depth-tested against the fill in the same pass."""
    from PySide6.QtQuick3D import QQuick3DGeometry

    solid = MeshGeometry()
    solid.meshView = quad_view
    assert solid.primitiveType() == QQuick3DGeometry.PrimitiveType.Triangles
    assert bytes(solid.indexData()) == bytes(quad_view.indexData())

    lines = MeshGeometry()
    lines.meshView = quad_view
    lines.topology = "lines"
    assert lines.primitiveType() == QQuick3DGeometry.PrimitiveType.Lines
    assert bytes(lines.indexData()) == bytes(quad_view.lineIndexData())
    assert bytes(lines.vertexData()) == bytes(quad_view.vertexData())  # shared verts
