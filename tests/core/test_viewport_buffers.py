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
from polycut.core.parts import UNASSIGNED_ID, Partition
from polycut.core.viewport import (
    build_highlight_buffers,
    build_highlight_lines,
    build_part_chunks,
)

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


def test_highlight_lines_are_the_edges_of_just_the_given_faces(textured_model):
    """The active-Part outline (#30) is the unique edges of only that Part's faces —
    so selecting one triangle of the quad outlines its 3 edges, not the whole mesh.
    Selecting both faces yields the same 5 deduped edges as the full mesh."""
    mesh = textured_model.geometry  # 2-triangle quad sharing the 0–2 diagonal

    edges = build_highlight_lines(mesh, [0])  # face 0 = verts (0, 1, 2)

    assert {tuple(int(v) for v in e) for e in edges} == {(0, 1), (1, 2), (0, 2)}
    assert len(build_highlight_lines(mesh, [0, 1])) == 5  # whole quad, diagonal deduped


def test_highlight_buffers_reuse_mesh_positions_and_outline_indices(textured_model):
    """The outline overlay reuses the fused mesh's own vertex positions (so the lines
    lie exactly on the surface) with a position-only stride, and a line-index buffer
    holding just the active Part's edges."""
    mesh = textured_model.geometry

    buffers = build_highlight_buffers(mesh, [0])

    positions = np.frombuffer(buffers.vertex_data, np.float32).reshape(buffers.vertex_count, 3)
    np.testing.assert_allclose(positions, mesh.vertices, atol=1e-6)
    assert buffers.stride == 12  # position only — 3 × float32
    pairs = np.frombuffer(buffers.index_data, np.uint32).reshape(-1, 2)
    assert buffers.line_count == 3
    assert {tuple(int(v) for v in p) for p in pairs} == {(0, 1), (1, 2), (0, 2)}


def _three_strip(normals=None):
    """Three separate triangles centred at x = −2, 0, +2 in the z=0 plane, with
    explicit per-vertex normals so a chunk can be checked for normal reuse."""
    verts, faces, norms = [], [], []
    normals = normals or [[0.0, 0.0, 1.0]] * 3
    for cx, normal in zip((-2.0, 0.0, 2.0), normals):
        b = len(verts)
        verts += [[cx - 0.3, -0.3, 0], [cx + 0.3, -0.3, 0], [cx, 0.4, 0]]
        norms += [normal] * 3
        faces.append([b, b + 1, b + 2])
    return trimesh.Trimesh(
        vertices=np.array(verts, float), faces=np.array(faces, np.int64),
        vertex_normals=np.array(norms, float), process=False,
    )


def _abc_partition():
    """Partition the three-strip: face 0 → Part A, face 2 → Part B, face 1 stays
    Unassigned — Parts on opposite sides of the model with the remainder in the middle."""
    partition = Partition.fresh(face_count=3)
    a = partition.create_part("A")
    partition.assign([0], a)
    b = partition.create_part("B")
    partition.assign([2], b)
    return partition, a, b


def test_part_chunks_offset_each_part_radially_with_unassigned_anchored():
    """Explode (#31) decomposes the mesh into one chunk per Part, each carrying its
    radial offset (part centroid − model centroid). The Parts on either side push out
    in opposite directions; the Unassigned remainder stays anchored at the origin."""
    mesh = _three_strip()
    partition, a, b = _abc_partition()

    chunks = {c.part_id: c for c in build_part_chunks(mesh, partition)}

    # model centroid sits at x = mean(−2, 0, 2) = 0
    np.testing.assert_allclose(chunks[a].offset, [-2.0, 0.0, 0.0], atol=1e-6)
    np.testing.assert_allclose(chunks[b].offset, [2.0, 0.0, 0.0], atol=1e-6)
    assert chunks[UNASSIGNED_ID].offset == (0.0, 0.0, 0.0)  # the remainder never moves


def test_part_chunks_partition_every_face_exactly_once():
    """The chunks together cover every face of the mesh, no gaps or overlaps — the
    exploded view shows the whole model. An empty Part contributes no chunk."""
    mesh = _three_strip()
    partition, _, _ = _abc_partition()

    chunks = build_part_chunks(mesh, partition)

    assert sum(c.triangle_count for c in chunks) == 3  # exhaustive over the 3 faces
    assert len(chunks) == 3  # Unassigned + A + B; none empty here


def test_part_chunks_reuse_the_fused_vertex_normals():
    """Each chunk reuses the fused mesh's own vertex normals (gathered, not recomputed
    via trimesh .submesh()), so the exploded chunks shade exactly like the assembled
    mesh. Deliberately non-geometric normals would differ under a recompute."""
    weird = [[0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]
    mesh = _three_strip(normals=weird)
    partition, a, _ = _abc_partition()

    chunk = {c.part_id: c for c in build_part_chunks(mesh, partition)}[a]

    floats = np.frombuffer(chunk.vertex_data, np.float32).reshape(chunk.vertex_count, -1)
    np.testing.assert_allclose(floats[:, 3:6], [[0.0, 1.0, 0.0]] * 3, atol=1e-6)  # Part A's normal


def test_buffers_expose_bounds_for_framing(textured_model):
    """The mesh's AABB travels with the buffers so the camera can frame it."""
    buffers = build_mesh_buffers(textured_model)

    lo, hi = textured_model.geometry.bounds
    np.testing.assert_allclose(buffers.bounds_min, lo, atol=1e-6)
    np.testing.assert_allclose(buffers.bounds_max, hi, atol=1e-6)
