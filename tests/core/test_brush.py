"""The spatial brush — manual carving tool #2 (#24), headless `core`.

The escape hatch for pieces colour can't separate (legs vs frame, same wood). Given
a surface hit point (from D's ray pick) and a **radius**, :class:`SpatialBrush`
range-queries faces whose **centroid** falls inside the sphere — *proximity, not
topology*, so it works across the shard soup where flood-fill is useless. A drag is
a sequence of hit points; the swept face set paints into the active Part (add) or
out of it (subtract) through slice A's ops, preserving the partition invariant. The
centroid KD-tree is built once per mesh and reused across drags.
"""

from __future__ import annotations

import numpy as np
import pytest
import trimesh

from polycut.core.brush import SpatialBrush
from polycut.core.parts import UNASSIGNED_ID, Partition
from polycut.core.picking import pick_face


def _tri_at(center, d=0.5):
    """A triangle whose centroid is exactly ``center`` (the mean of its three
    vertices), built from symmetric offsets that sum to zero. ``d=0.5`` keeps the
    arithmetic exact in binary, so boundary distances land on clean values."""
    cx, cy, cz = center
    return [[cx - d, cy - d, cz], [cx + d, cy - d, cz], [cx, cy + 2 * d, cz]]


def _centroid_mesh(centers):
    """A mesh of independent triangles, one per centroid in ``centers`` (face id i ↔
    centers[i]). Only the centroids matter to the brush; ``process=False`` keeps the
    triangles from being merged or reordered."""
    verts, faces = [], []
    for c in centers:
        base = len(verts)
        verts += _tri_at(c)
        faces.append([base, base + 1, base + 2])
    return trimesh.Trimesh(vertices=np.array(verts, float), faces=np.array(faces, np.int64), process=False)


def test_brush_selects_faces_whose_centroid_is_within_the_radius():
    """A range query at a point returns exactly the faces whose centroid lies inside
    the sphere — the one just outside is left out."""
    mesh = _centroid_mesh([(0, 0, 0), (1, 0, 0), (3, 0, 0)])  # centroids on the x-axis

    brush = SpatialBrush(mesh)
    selected = brush.faces_within(point=[0, 0, 0], radius=1.5)

    assert set(selected) == {0, 1}  # x=0 and x=1 are within 1.5; x=3 is not


def test_a_centroid_exactly_on_the_radius_is_included():
    """The sphere is closed — a centroid sitting exactly at distance ``radius`` counts
    as inside, so a brush sized to just reach a face does reach it."""
    mesh = _centroid_mesh([(0, 0, 0), (1, 0, 0)])  # the second centroid is 1.0 away

    brush = SpatialBrush(mesh)

    assert set(brush.faces_within(point=[0, 0, 0], radius=1.0)) == {0, 1}  # 1.0 == radius → in
    assert set(brush.faces_within(point=[0, 0, 0], radius=0.999)) == {0}  # just short → out


def test_a_larger_radius_is_a_superset_of_a_smaller_one():
    """Growing the brush only adds faces, never drops them — the knob the designer
    drags from tight to loose without the selection flickering."""
    mesh = _centroid_mesh([(x, 0, 0) for x in range(6)])  # centroids at x=0..5
    brush = SpatialBrush(mesh)

    small = set(brush.faces_within(point=[0, 0, 0], radius=2.0))
    large = set(brush.faces_within(point=[0, 0, 0], radius=4.0))

    assert small == {0, 1, 2}
    assert small < large  # strict superset — the bigger sphere reaches more faces


def test_painting_a_drag_assigns_the_whole_swept_set_and_holds_the_invariant():
    """A drag is a sequence of hit points; painting it moves the union of every
    point's brushed faces into the active Part. Faces under no point stay where they
    were, and the partition stays exhaustive + non-overlapping."""
    mesh = _centroid_mesh([(x, 0, 0) for x in range(6)])  # centroids at x=0..5
    brush = SpatialBrush(mesh)
    partition = Partition.fresh(face_count=6)
    active = partition.create_part(name="legs")

    brush.paint(partition, points=[[0, 0, 0], [5, 0, 0]], radius=1.0, part_id=active)

    labels = partition.labels
    assert set(np.where(labels == active)[0]) == {0, 1, 4, 5}  # union of both brush stamps
    assert set(np.where(labels == UNASSIGNED_ID)[0]) == {2, 3}  # the gap between stamps
    assert sum(partition.face_count(p.id) for p in partition.parts) == 6  # exhaustive


def test_erasing_returns_only_the_active_parts_own_faces_to_unassigned():
    """Erasing subtracts the swept set from the active Part, but only the faces that
    Part actually owns — brushing over a neighbouring Part doesn't steal its faces,
    it just refines your own."""
    mesh = _centroid_mesh([(x, 0, 0) for x in range(6)])  # centroids at x=0..5
    brush = SpatialBrush(mesh)
    partition = Partition.fresh(face_count=6)
    legs = partition.create_part(name="legs")
    frame = partition.create_part(name="frame")

    brush.paint(partition, points=[[x, 0, 0] for x in (0, 1, 2, 3)], radius=0.4, part_id=legs)
    brush.paint(partition, points=[[4, 0, 0], [5, 0, 0]], radius=0.4, part_id=frame)

    # erase a drag that sweeps faces of both Parts, off the active (legs) Part
    brush.erase(partition, points=[[x, 0, 0] for x in (2, 3, 4, 5)], radius=0.4, part_id=legs)

    labels = partition.labels
    assert set(np.where(labels == legs)[0]) == {0, 1}        # legs' own swept faces left
    assert set(np.where(labels == UNASSIGNED_ID)[0]) == {2, 3}  # returned to the remainder
    assert set(np.where(labels == frame)[0]) == {4, 5}       # frame untouched by the erase
    assert sum(partition.face_count(p.id) for p in partition.parts) == 6


@pytest.mark.slow
def test_brush_paints_a_local_patch_on_the_real_sofa(simplified_sofa):
    """End-to-end at carving scale: D's ray finds a face on the real 646k-derived
    mesh, the brush paints a sphere around that hit point into a Part, and the
    partition stays exhaustive. The clicked face is always under the brush; the patch
    is local, not the whole model."""
    mesh = simplified_sofa[0].geometry
    lo, hi = mesh.bounds
    centre = (lo + hi) / 2

    seed = pick_face(mesh, origin=[centre[0], hi[1] + 10.0, centre[2]], direction=[0, -1, 0])
    assert seed is not None  # the ray lands on the top of the sofa
    hit = mesh.triangles_center[seed]
    radius = 0.05 * float(np.linalg.norm(hi - lo))  # 5% of the bounding-box diagonal

    brush = SpatialBrush(mesh)
    partition = Partition.fresh(face_count=len(mesh.faces))
    cushion = partition.create_part(name="cushion")
    brush.paint(partition, points=[hit], radius=radius, part_id=cushion)

    painted = set(np.where(partition.labels == cushion)[0])
    assert seed in painted  # the face the ray hit sits under the brush (centroid dist 0)
    assert 0 < len(painted) < len(mesh.faces)  # a local patch, not the entire mesh
    assert sum(partition.face_count(p.id) for p in partition.parts) == len(mesh.faces)
