"""Auto colour-cluster — split the mesh's faces into Parts by baked-texture colour.

The MVP-3 hero tool (#21), pure headless ``core``. Per-face colour is the texel at
the mean of the face's three vertex UVs; k-means in CIELAB groups those colours
into Parts (wood vs fabric at K=2). The segmentation is **mesh-agnostic**
(``segment(mesh, texture) -> per-face labels``); ``split_by_colour`` applies it
through slice A's :class:`Partition` ops so the invariant holds.

Strong, deterministic assertions run on a tiny two-colour synthetic mesh; the real
646k Meshy sofa is exercised in a ``slow`` test.
"""

from __future__ import annotations

import numpy as np
import pytest
import trimesh
from PIL import Image

from polycut.core.parts import UNASSIGNED_ID, Partition
from polycut.core.segment import face_colours, segment, split_by_colour

BROWN = (120, 72, 36)
GREY = (160, 160, 160)


def _two_colour_mesh():
    """A 2-face mesh over a 2×1 texture: left texel BROWN, right texel GREY, with
    face 0's UVs in the left texel and face 1's in the right."""
    texture = np.array([[BROWN, GREY]], dtype=np.uint8)  # shape (1, 2, 3)
    verts = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=float)
    faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    # face 0 vertices all in the left half (u<0.5), face 1's all in the right half.
    uv = np.array([[0.1, 0.5], [0.2, 0.5], [0.8, 0.5], [0.9, 0.5]])
    mesh = trimesh.Trimesh(
        vertices=verts,
        faces=faces,
        visual=trimesh.visual.TextureVisuals(uv=uv),
        process=False,
    )
    return mesh, texture


def test_face_colour_is_the_texel_at_the_mean_uv():
    """Each face's colour is the texel sampled at the mean of its three vertex UVs."""
    mesh, texture = _two_colour_mesh()

    colours = face_colours(mesh, texture)

    assert tuple(colours[0]) == BROWN  # face 0 sampled the left texel
    assert tuple(colours[1]) == GREY   # face 1 sampled the right texel


def _striped_mesh(n_each):
    """``n_each`` independent BROWN-UV faces followed by ``n_each`` GREY-UV faces,
    over the same 2×1 texture — a clean two-material mesh for clustering."""
    texture = np.array([[BROWN, GREY]], dtype=np.uint8)
    us = [0.2] * n_each + [0.8] * n_each  # left = brown, right = grey
    verts, faces, uv = [], [], []
    for i, u in enumerate(us):
        base = 3 * i
        verts += [[i, 0, 0], [i + 1, 0, 0], [i, 1, 0]]
        faces.append([base, base + 1, base + 2])
        uv += [[u, 0.5]] * 3
    mesh = trimesh.Trimesh(
        vertices=np.array(verts, float),
        faces=np.array(faces, np.int64),
        visual=trimesh.visual.TextureVisuals(uv=np.array(uv)),
        process=False,
    )
    return mesh, texture, n_each


def test_segment_k2_separates_the_two_colours():
    """k-means at K=2 puts every brown face in one cluster and every grey face in the
    other — the wood-vs-fabric split that makes the hero action one click."""
    mesh, texture, n = _striped_mesh(n_each=20)

    labels = segment(mesh, texture, k=2)

    brown_labels, grey_labels = labels[:n], labels[n:]
    assert len(np.unique(labels)) == 2
    assert len(np.unique(brown_labels)) == 1  # all brown faces together
    assert len(np.unique(grey_labels)) == 1   # all grey faces together
    assert brown_labels[0] != grey_labels[0]  # in different clusters


def test_split_scoped_to_unassigned_leaves_existing_parts_untouched():
    """Split-by-material runs on Unassigned by default: it carves k new Parts from the
    not-yet-assigned faces and never disturbs Parts the designer already made."""
    mesh, texture, _ = _striped_mesh(n_each=20)
    partition = Partition.fresh(face_count=40)
    kept = partition.create_part(name="hand-picked")
    partition.assign([0, 1, 2], kept)  # carve a Part out by hand first

    new_ids = split_by_colour(partition, mesh, texture, k=2)

    labels = partition.labels
    assert set(np.where(labels == kept)[0]) == {0, 1, 2}  # untouched
    assert len(new_ids) == 2
    assert partition.face_count(UNASSIGNED_ID) == 0       # every loose face now carved
    assert sum(partition.face_count(p.id) for p in partition.parts) == 40


def test_split_scoped_to_a_part_subdivides_only_that_part():
    """Scoped to a Part, the split subdivides just that Part's faces by colour and
    leaves every other Part alone — breaking a mixed group apart without re-clustering
    the whole model."""
    mesh, texture, _ = _striped_mesh(n_each=20)  # 0–19 brown, 20–39 grey
    partition = Partition.fresh(face_count=40)
    keep = partition.create_part(name="keep")
    partition.assign([38, 39], keep)             # an unrelated Part, must survive
    mixed = partition.create_part(name="mixed")
    partition.assign(np.arange(0, 38), mixed)    # brown + grey in one Part

    new_ids = split_by_colour(partition, mesh, texture, k=2, scope=mixed)

    labels = partition.labels
    assert set(np.where(labels == keep)[0]) == {38, 39}            # untouched
    assert mixed not in [p.id for p in partition.parts]            # fully subdivided
    owners = {tuple(np.where(labels == nid)[0].tolist()) for nid in new_ids}
    assert tuple(range(0, 20)) in owners                           # brown subset
    assert tuple(range(20, 38)) in owners                          # grey subset
    assert sum(partition.face_count(p.id) for p in partition.parts) == 40


def test_split_on_an_empty_scope_is_a_no_op():
    """Splitting when the scope holds no faces (e.g. everything is already carved)
    creates no Parts and leaves the partition untouched, rather than failing."""
    mesh, texture, _ = _striped_mesh(n_each=20)
    partition = Partition.fresh(face_count=40)
    everything = partition.create_part(name="everything")
    partition.assign(np.arange(40), everything)  # Unassigned now empty

    new_ids = split_by_colour(partition, mesh, texture, k=2, scope=UNASSIGNED_ID)

    assert new_ids == []
    assert [p.id for p in partition.parts] == [UNASSIGNED_ID, everything]
    assert partition.face_count(everything) == 40


@pytest.mark.slow
def test_split_by_colour_separates_wood_from_fabric_on_the_real_sofa(simplified_sofa, sofa_model):
    """On the 646k Meshy sofa, K=2 split-by-material yields two substantial,
    colour-distinct Parts (wood vs fabric) and the partition still covers every
    face — the headline demo, exercised on real baked geometry."""
    mesh = simplified_sofa[0].geometry
    texture = np.asarray(Image.open(sofa_model.texture_path).convert("RGB"))
    partition = Partition.fresh(face_count=int(mesh.faces.shape[0]))

    new_ids = split_by_colour(partition, mesh, texture, k=2)

    sizes = [partition.face_count(pid) for pid in new_ids]
    assert min(sizes) > 0.05 * mesh.faces.shape[0]          # a real split, not 99/1
    assert partition.face_count(UNASSIGNED_ID) == 0
    assert sum(partition.face_count(p.id) for p in partition.parts) == mesh.faces.shape[0]

    means = [face_colours(mesh, texture)[np.where(partition.labels == pid)].mean(axis=0) for pid in new_ids]
    assert np.linalg.norm(means[0] - means[1]) > 20          # visibly different colours
