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

from polycut.core import build_mesh_buffers, load_source_model
from polycut.core.model import SourceModel

MULTI_OBJECT = (
    Path(__file__).resolve().parents[1] / "fixtures" / "multi_object" / "two_cubes.obj"
)


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


@pytest.fixture
def multi_object_model():
    """A Scene of two separate quads — the multi-object case. trimesh loads a
    multi-material OBJ as a Scene, not a single Trimesh, so the viewport buffer
    builder has to cope with one."""
    def quad(x):
        return trimesh.Trimesh(
            vertices=np.array(
                [[x, 0, 0], [x + 1, 0, 0], [x + 1, 1, 0], [x, 1, 0]], dtype=np.float64
            ),
            faces=np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64),
            vertex_normals=np.tile([0.0, 0.0, 1.0], (4, 1)),
            process=False,
        )
    scene = trimesh.Scene([quad(0.0), quad(2.0)])
    return SourceModel(
        source_path=Path("two.obj"),
        geometry=scene,
        face_count=4,
        object_count=2,
        texture_path=None,
    )


def test_scene_model_buffers_fuse_every_geometry(multi_object_model):
    """A multi-geometry model renders as one fused mesh — the viewport draws the
    whole model, so its buffers carry every geometry's triangles and vertices, not
    just the first. Without this a multi-object model renders blank."""
    buffers = build_mesh_buffers(multi_object_model)

    assert buffers.triangle_count == 4  # both quads, 2 triangles each
    assert buffers.vertex_count == 8  # both quads, 4 vertices each
    assert buffers.line_count > 0  # edges built off the fused mesh


def test_committed_multi_object_fixture_loads_and_fuses():
    """The multi-material validation fixture loads as two outliner rows and its
    buffers fuse both cubes — the real-file multi-object path, end to end."""
    model = load_source_model(MULTI_OBJECT)

    assert [(o.name, o.face_count) for o in model.objects] == [
        ("two_cubes", 12),
        ("two_cubes.1", 12),
    ]

    buffers = build_mesh_buffers(model)
    assert buffers.triangle_count == 24
    assert buffers.vertex_count == 16


def test_scene_buffers_carry_the_parts_own_normals():
    """Fusing a multi-geometry model carries each part's own vertex normals into
    the buffer instead of recomputing them (the recompute path needs scipy and
    prints a noisy fallback). Parts here carry deliberately non-geometric normals,
    so a recompute would visibly differ from what's preserved."""
    def quad(x, normal):
        return trimesh.Trimesh(
            vertices=np.array(
                [[x, 0, 0], [x + 1, 0, 0], [x + 1, 1, 0], [x, 1, 0]], dtype=np.float64
            ),
            faces=np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64),
            vertex_normals=np.tile(normal, (4, 1)),  # not the geometric [0,0,1]
            process=False,
        )
    scene = trimesh.Scene([quad(0.0, [0, 1, 0]), quad(2.0, [1, 0, 0])])
    model = SourceModel(
        source_path=Path("two.obj"),
        geometry=scene,
        face_count=4,
        object_count=2,
        texture_path=None,
    )

    buffers = build_mesh_buffers(model)
    normals = _vertex_floats(buffers)[:, 3:6]

    expected = np.vstack([np.tile([0, 1, 0], (4, 1)), np.tile([1, 0, 0], (4, 1))])
    np.testing.assert_allclose(normals, expected, atol=1e-6)


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


def test_line_indices_are_the_unique_triangle_edges(textured_model):
    """The Wireframe / Edges modes draw the mesh as lines: the buffer holds each
    triangle edge once (shared edges deduped), so a 2-triangle quad — which shares
    one diagonal — yields 5 edges, not 6. Drawn in the same pass as the solid so
    hidden edges are depth-occluded (#9)."""
    buffers = build_mesh_buffers(textured_model)

    pairs = np.frombuffer(buffers.line_index_data, dtype=np.uint32).reshape(-1, 2)

    assert buffers.line_count == 5  # 4 perimeter + 1 shared diagonal, deduped
    assert pairs.shape == (5, 2)
    assert pairs.max() < buffers.vertex_count
    assert (pairs[:, 0] < pairs[:, 1]).all()  # each edge stored low→high
    assert len({tuple(p) for p in pairs}) == 5  # no duplicates


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
