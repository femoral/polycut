"""Per-vertex Part colours for the flat-colour Parts view (#26).

The viewport's "parts" mode paints every face in its Part's swatch colour. The
GPU buffer is per-vertex (it shares the existing indexed vertex buffer), so this
seam scatters each face's Part colour onto its three vertices. Pure numpy, no Qt
and no GPU — the render itself is HITL; here we pin the colour assignment.
"""

from __future__ import annotations

import numpy as np
import trimesh

from polycut.core.parts import UNASSIGNED_COLOUR, UNASSIGNED_ID, Partition
from polycut.core.viewport import build_part_buffers, build_part_colours


def _quad():
    """A 2-triangle quad with 4 vertices — the minimal mesh to interleave."""
    return trimesh.Trimesh(
        vertices=np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=np.float64),
        faces=np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64),
        process=False,
    )


def test_fresh_partition_paints_every_vertex_the_unassigned_grey():
    """With nothing carved yet, every face is Unassigned — so every vertex takes
    the neutral remainder grey at full opacity."""
    faces = np.array([[0, 1, 2], [2, 3, 4]])
    partition = Partition.fresh(face_count=len(faces))

    colours = build_part_colours(partition, faces, vertex_count=5)

    expected = np.array([*UNASSIGNED_COLOUR]) / 255.0
    assert colours.shape == (5, 4)
    assert np.allclose(colours[:, :3], expected)
    assert np.allclose(colours[:, 3], 1.0)


def test_a_carved_face_paints_its_part_colour_onto_its_vertices():
    """Assigning a face to a Part paints that Part's swatch colour onto the face's
    three vertices; the untouched face stays the Unassigned grey."""
    faces = np.array([[0, 1, 2], [2, 3, 4]])
    partition = Partition.fresh(face_count=len(faces))
    part_id = partition.create_part(name="Seat")
    partition.assign([0], part_id)  # first triangle → the new Part

    colours = build_part_colours(partition, faces, vertex_count=5)

    seat = np.array([*partition.part(part_id).colour]) / 255.0
    grey = np.array([*UNASSIGNED_COLOUR]) / 255.0
    assert np.allclose(colours[0, :3], seat)  # vertices of the carved face
    assert np.allclose(colours[1, :3], seat)
    assert np.allclose(colours[3, :3], grey)  # vertex of the untouched face
    assert np.allclose(colours[4, :3], grey)


def test_a_hidden_part_drops_its_vertices_to_zero_alpha():
    """Toggling a Part hidden in the outliner zeroes the alpha on its faces'
    vertices, so the flat-colour view can blend it away; visible Parts stay opaque."""
    faces = np.array([[0, 1, 2], [2, 3, 4]])
    partition = Partition.fresh(face_count=len(faces))
    part_id = partition.create_part(name="Seat")
    partition.assign([0], part_id)
    partition.set_visible(part_id, False)

    colours = build_part_colours(partition, faces, vertex_count=5)

    assert np.allclose(colours[0, 3], 0.0)  # vertices of the hidden Part
    assert np.allclose(colours[1, 3], 0.0)
    assert np.allclose(colours[3, 3], 1.0)  # the still-visible remainder
    assert np.allclose(colours[4, 3], 1.0)


def test_a_vertex_shared_across_parts_takes_the_higher_id_part():
    """Welded buffer: a vertex shared by faces in two Parts can hold one colour.
    The later-created (higher-id) Part wins — a deterministic, documented seam (the
    boundary artifact is negligible on the largely-split Meshy soup)."""
    faces = np.array([[0, 1, 2], [2, 3, 4]])  # vertex 2 is shared by both faces
    partition = Partition.fresh(face_count=len(faces))
    first = partition.create_part(name="Seat")
    second = partition.create_part(name="Legs")
    partition.assign([0], first)
    partition.assign([1], second)

    colours = build_part_colours(partition, faces, vertex_count=5)

    legs = np.array([*partition.part(second).colour]) / 255.0
    assert np.allclose(colours[2, :3], legs)  # higher id wins the shared vertex


def test_active_part_is_brightened_as_the_selection_highlight():
    """Selecting a Part highlights it in the flat-colour view: its faces' vertices
    brighten toward white, while the other Parts keep their colour — so the active
    edit target reads at a glance. With no Part selected (Unassigned active), nothing
    is emphasised."""
    faces = np.array([[0, 1, 2], [2, 3, 4]])
    partition = Partition.fresh(face_count=len(faces))
    a = partition.create_part(name="A")
    b = partition.create_part(name="B")
    partition.assign([0], a)  # face 0 → A (vertices 0,1)
    partition.assign([1], b)  # face 1 → B (vertices 3,4)

    base = build_part_colours(partition, faces, vertex_count=5)
    highlighted = build_part_colours(partition, faces, vertex_count=5, active_id=a)

    assert np.all(highlighted[0, :3] >= base[0, :3])  # A's vertex never darkens
    assert np.any(highlighted[0, :3] > base[0, :3])   # …and is brighter
    assert np.allclose(highlighted[3, :3], base[3, :3])  # B (not active) unchanged
    # Default (no active Part) leaves every colour untouched.
    assert np.allclose(build_part_colours(partition, faces, 5, UNASSIGNED_ID), base)


def test_part_buffers_interleave_positions_then_rgba():
    """The flat-colour view uploads one interleaved buffer: each vertex is its
    position (floats 0..3) followed by its Part RGBA (floats 3..7), so the GPU
    draws the mesh in place, coloured. Indices match the mesh faces."""
    mesh = _quad()
    partition = Partition.fresh(face_count=len(mesh.faces))

    buffers = build_part_buffers(mesh, partition)

    floats = np.frombuffer(buffers.vertex_data, dtype=np.float32).reshape(
        buffers.vertex_count, -1
    )
    grey = np.array([*UNASSIGNED_COLOUR]) / 255.0
    assert buffers.vertex_count == 4
    assert buffers.triangle_count == 2
    assert buffers.stride == 7 * 4  # pos3 + rgba4, float32
    np.testing.assert_allclose(floats[:, 0:3], mesh.vertices, atol=1e-6)
    assert np.allclose(floats[:, 3:6], grey, atol=1e-6)
    assert np.allclose(floats[:, 6], 1.0)
    indices = np.frombuffer(buffers.index_data, dtype=np.uint32).reshape(-1, 3)
    np.testing.assert_array_equal(indices, mesh.faces)
