"""Pure mesh → GPU-buffer builder for the Qt3D viewport (#8).

The viewport renders the *current* model — the same faithful geometry the
exporter writes. :func:`build_mesh_buffers` turns a loaded ``SourceModel`` into
the interleaved vertex buffer + index buffer a ``QQuick3DGeometry`` uploads,
with no Qt dependency so the translation stays in the headless test seam. These
tests pin what the renderer consumes; the actual shaded render is HITL (#15).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import trimesh

from polycut.core import build_mesh_buffers
from polycut.core.model import SourceModel


def _vertex_floats(buffers):
    """Decode the interleaved vertex buffer as one row of float32 per vertex."""
    floats = np.frombuffer(buffers.vertex_data, dtype=np.float32)
    return floats.reshape(buffers.vertex_count, -1)


@pytest.fixture
def untextured_model():
    """A mesh with no UVs — the missing-texture case Meshy sometimes ships."""
    vertices = np.array(
        [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=np.float64
    )
    faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    normals = np.tile([0.0, 0.0, 1.0], (4, 1))
    mesh = trimesh.Trimesh(
        vertices=vertices, faces=faces, vertex_normals=normals, process=False
    )  # default ColorVisuals — no .uv
    return SourceModel(
        source_path=Path("untextured.obj"),
        geometry=mesh,
        face_count=2,
        object_count=1,
        texture_path=None,
    )


@pytest.fixture
def textured_model(tmp_path):
    """A tiny quad with explicit normals + UVs + a baked texture, no scipy needed.

    Stands in for a real Meshy mesh (which always ships ``vn`` and UVs) while
    staying fast and fully controlled — every attribute is known exactly.
    """
    vertices = np.array(
        [[0, 0, 0], [2, 0, 0], [2, 3, 0], [0, 3, 0]], dtype=np.float64
    )
    faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    normals = np.tile([0.0, 0.0, 1.0], (4, 1))
    uv = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float64)
    mesh = trimesh.Trimesh(
        vertices=vertices,
        faces=faces,
        vertex_normals=normals,
        visual=trimesh.visual.TextureVisuals(uv=uv),
        process=False,
    )
    texture = tmp_path / "baked.png"
    texture.write_bytes(b"\x89PNG\r\n")  # a real file path for the material to load
    return SourceModel(
        source_path=tmp_path / "quad.obj",
        geometry=mesh,
        face_count=2,
        object_count=1,
        texture_path=texture,
    )


def test_buffers_report_mesh_counts(textured_model):
    """Building buffers from a loaded model reports its triangle + vertex counts."""
    buffers = build_mesh_buffers(textured_model)

    assert buffers.triangle_count == textured_model.face_count
    assert buffers.vertex_count == len(textured_model.geometry.vertices)


def test_vertex_buffer_carries_positions(textured_model):
    """The GPU receives each vertex's real position (first 3 floats per vertex)."""
    buffers = build_mesh_buffers(textured_model)

    positions = _vertex_floats(buffers)[:, 0:3]

    np.testing.assert_allclose(
        positions, textured_model.geometry.vertices, rtol=0, atol=1e-6
    )
    assert buffers.stride == _vertex_floats(buffers).shape[1] * 4  # bytes per vertex


def test_index_buffer_references_triangles(textured_model):
    """Each triangle indexes three vertices, matching the model's faces."""
    buffers = build_mesh_buffers(textured_model)

    indices = np.frombuffer(buffers.index_data, dtype=np.uint32).reshape(-1, 3)

    assert len(indices) == buffers.triangle_count
    np.testing.assert_array_equal(indices, textured_model.geometry.faces)


def test_vertex_buffer_carries_normals(textured_model):
    """Each vertex carries its normal (floats 3..6) so the mesh shades, not flat."""
    buffers = build_mesh_buffers(textured_model)

    normals = _vertex_floats(buffers)[:, 3:6]

    np.testing.assert_allclose(
        normals, textured_model.geometry.vertex_normals, rtol=0, atol=1e-6
    )


def test_vertex_buffer_carries_uvs(textured_model):
    """Each vertex carries its UV (floats 6..8) so the baked texture maps on."""
    buffers = build_mesh_buffers(textured_model)

    uvs = _vertex_floats(buffers)[:, 6:8]

    np.testing.assert_allclose(
        uvs, textured_model.geometry.visual.uv, rtol=0, atol=1e-6
    )


def test_untextured_model_still_builds_a_valid_buffer(untextured_model):
    """No UVs is not an error — the layout stays stable, UVs default to zero."""
    buffers = build_mesh_buffers(untextured_model)

    floats = _vertex_floats(buffers)
    assert buffers.vertex_count == 4
    assert floats.shape[1] == 8  # pos3 + norm3 + uv2 — stable with or without UVs
    np.testing.assert_array_equal(floats[:, 6:8], 0.0)


def test_buffers_expose_bounds_for_framing(textured_model):
    """The mesh's AABB travels with the buffers so the camera can frame it."""
    buffers = build_mesh_buffers(textured_model)

    lo, hi = textured_model.geometry.bounds
    np.testing.assert_allclose(buffers.bounds_min, lo, atol=1e-6)
    np.testing.assert_allclose(buffers.bounds_max, hi, atol=1e-6)
