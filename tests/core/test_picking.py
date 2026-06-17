"""Face picking + the colour wand — manual carving tool #1 (#23), headless `core`.

Given a world-space ray (the bridge builds it from screen (x,y) + camera later),
:func:`pick_face` returns the hit face id; this slice owns the geometry maths only.
The :func:`colour_wand` grows a selection from a seed face by baked-texture colour
(reusing slice B): **local** mode is a contiguous flood-fill across edge-shared
faces (so a click stays on the piece it landed on, even across the soup), **global**
grabs every same-colour face anywhere. Selections add to / subtract from the active
Part through slice A's ops, preserving the partition invariant.
"""

from __future__ import annotations

import numpy as np
import pytest
import trimesh
from PIL import Image

from polycut.core.parts import UNASSIGNED_ID, Partition
from polycut.core.picking import add_to_part, colour_wand, pick_face, subtract_from_part

BROWN = (120, 72, 36)
BROWN2 = (130, 82, 46)  # ~4.1 Lab from BROWN (a near shade)
GREY = (160, 160, 160)  # ~45 Lab from BROWN (clearly different)


def _quad_z0():
    """Two triangles tiling the unit square in the z=0 plane: face 0 is the lower-right
    triangle (y<x), face 1 the upper-left."""
    verts = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=float)
    faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    return trimesh.Trimesh(vertices=verts, faces=faces, process=False)


def test_ray_returns_the_face_it_hits():
    """A ray dropped straight down onto a known triangle returns that face's id."""
    mesh = _quad_z0()

    hit = pick_face(mesh, origin=[0.7, 0.3, 5.0], direction=[0.0, 0.0, -1.0])

    assert hit == 0  # (0.7, 0.3) lies in the lower-right triangle


def test_nearest_face_wins_when_the_ray_crosses_several():
    """A ray through stacked faces returns the closest one to the origin, not a
    face hidden behind it."""
    verts = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0],   # face 0 at z=0 (far)
         [0, 0, 1], [1, 0, 1], [0, 1, 1]],  # face 1 at z=1 (near the descending ray)
        dtype=float,
    )
    faces = np.array([[0, 1, 2], [3, 4, 5]], dtype=np.int64)
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=False)

    hit = pick_face(mesh, origin=[0.3, 0.3, 5.0], direction=[0.0, 0.0, -1.0])

    assert hit == 1  # the z=1 face is nearer to the ray origin than the z=0 face


def test_ray_that_misses_returns_no_hit():
    """A ray pointing away from all geometry returns None — the bridge treats that as
    an empty click."""
    mesh = _quad_z0()

    hit = pick_face(mesh, origin=[5.0, 5.0, 5.0], direction=[0.0, 0.0, -1.0])

    assert hit is None


def _wand_mesh():
    """A mesh of four disconnected pieces over a 3-texel texture [BROWN, BROWN2, GREY]:

    - island A: faces 0,1 (BROWN), edge-connected to each other
    - island B: faces 2,3 (BROWN), connected to each other but NOT to A
    - island C: face 4 (BROWN2, a near shade), on its own
    - island D: face 5 (GREY), on its own

    Vertices are shared only within an island, so ``face_adjacency`` links 0–1 and
    2–3 and nothing across pieces — exactly the soup the wand must respect.
    """
    texture = np.array([[BROWN, BROWN2, GREY]], dtype=np.uint8)  # (1, 3, 3)
    quads = [  # (vertex block, the two triangles' local indices, texel column)
        (0, [(0, 1, 2), (0, 2, 3)], 0),   # A → BROWN  (u in col 0)
        (4, [(0, 1, 2), (0, 2, 3)], 0),   # B → BROWN
        (8, [(0, 1, 2)], 1),              # C → BROWN2 (u in col 1)
        (11, [(0, 1, 2)], 2),             # D → GREY   (u in col 2)
    ]
    us = [1 / 6, 1 / 2, 5 / 6]  # centre of each of the 3 texels
    verts, faces, uv = [], [], []
    for base, tris, col in quads:
        for k in range(4 if len(tris) == 2 else 3):
            verts.append([base + k, col, 0])  # positions only need to be distinct
            uv.append([us[col], 0.5])
        for tri in tris:
            faces.append([base + i for i in tri])
    mesh = trimesh.Trimesh(
        vertices=np.array(verts, float),
        faces=np.array(faces, np.int64),
        visual=trimesh.visual.TextureVisuals(uv=np.array(uv)),
        process=False,
    )
    return mesh, texture


def test_wand_global_grabs_every_matching_face_anywhere():
    """Global mode selects all faces within the Lab threshold regardless of where they
    sit — the scattered-pattern / select-by-colour case — but stops at the threshold
    (grey is left out)."""
    mesh, texture = _wand_mesh()

    selected = colour_wand(mesh, texture, seed=0, threshold=10.0, mode="global")

    assert set(selected) == {0, 1, 2, 3, 4}  # both BROWN islands + the near BROWN2, not GREY


def test_wand_local_stays_on_the_clicked_piece():
    """Local mode flood-fills only the contiguous patch under the seed: island B is the
    same colour but disconnected, so it is left out — a click on the cushion doesn't
    grab matching faces across the model."""
    mesh, texture = _wand_mesh()

    selected = colour_wand(mesh, texture, seed=0, threshold=10.0, mode="local")

    assert set(selected) == {0, 1}  # island A only; B (disconnected, same colour) excluded


def test_tightening_the_threshold_shrinks_the_selection():
    """A tighter threshold counts fewer faces as 'similar' — the near BROWN2 shade is in
    at a loose threshold and out at a tight one, the knob the designer tunes."""
    mesh, texture = _wand_mesh()

    loose = colour_wand(mesh, texture, seed=0, threshold=10.0, mode="global")
    tight = colour_wand(mesh, texture, seed=0, threshold=2.0, mode="global")

    assert 4 in set(loose)            # BROWN2 (~4.1 Lab) counts as similar when loose
    assert 4 not in set(tight)        # but not when tight
    assert {0, 1, 2, 3} <= set(tight)  # the exact-BROWN faces survive either way


def test_add_and_subtract_refine_the_active_part_and_hold_the_invariant():
    """A selection adds to the active Part (stealing the faces) and subtracts from it
    (returning only its own faces to Unassigned), refining a Part incrementally while
    the partition stays exhaustive and non-overlapping."""
    partition = Partition.fresh(face_count=6)
    active = partition.create_part(name="cushions")

    add_to_part(partition, [0, 1, 2, 3, 4], active)
    assert partition.face_count(active) == 5
    assert sum(partition.face_count(p.id) for p in partition.parts) == 6

    subtract_from_part(partition, [2, 3, 5], active)  # 5 isn't the active Part's — ignored
    labels = partition.labels
    assert set(np.where(labels == active)[0]) == {0, 1, 4}
    assert set(np.where(labels == UNASSIGNED_ID)[0]) == {2, 3, 5}
    assert sum(partition.face_count(p.id) for p in partition.parts) == 6


@pytest.mark.slow
def test_pick_and_wand_work_on_the_real_sofa(simplified_sofa):
    """On the real 646k-derived mesh, a ray finds a face and the wand grows from it —
    the hand-rolled picker + flood-fill hold up at carving scale (no rtree/embree)."""
    mesh = simplified_sofa[0].geometry
    texture = np.asarray(Image.open(simplified_sofa[0].texture_path).convert("RGB"))
    lo, hi = mesh.bounds
    centre = (lo + hi) / 2

    seed = pick_face(mesh, origin=[centre[0], hi[1] + 10.0, centre[2]], direction=[0, -1, 0])
    assert seed is not None  # the ray finds the top of the sofa

    local = colour_wand(mesh, texture, seed=seed, threshold=10.0, mode="local")
    global_ = colour_wand(mesh, texture, seed=seed, threshold=10.0, mode="global")
    assert seed in set(local)              # the patch contains its seed
    assert len(local) <= len(global_)      # local is bounded by the global match set
