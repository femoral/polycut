"""Auto colour-cluster — carve Parts from baked-texture colour (the hero tool).

A Meshy Source model is a topological soup under one baked material, so a Part
boundary (frame vs cushion) survives only in **per-face baked-texture colour**
(ADR-0004). This module samples that colour and clusters it:

- :func:`face_colours` — each face's colour is the texel at the mean of its three
  vertex UVs.
- :func:`segment` — k-means in CIELAB over those colours → per-face labels. Kept
  **mesh-agnostic** (blind to original vs cut) so cut-first ordering and per-part
  decimation can drop in later.
- :func:`split_by_colour` — applies a segmentation through slice A's
  :class:`~polycut.core.parts.Partition`, scoped to Unassigned (default) or one
  Part, so the partition invariant always holds.
"""

from __future__ import annotations

import numpy as np
from skimage.color import rgb2lab
from sklearn.cluster import KMeans

from polycut.core.parts import UNASSIGNED_ID, Partition


def face_colours(mesh, texture: np.ndarray) -> np.ndarray:
    """Per-face baked colour: the texel at the mean of each face's vertex UVs.

    ``texture`` is an ``(H, W, 3)`` RGB array. UV ``v`` is bottom-up, image rows are
    top-down, so the row is flipped. Returns an ``(n_faces, 3)`` ``uint8`` array.
    """
    mean_uv = mesh.visual.uv[mesh.faces].mean(axis=1)  # (n_faces, 2)
    height, width = texture.shape[:2]
    cols = np.clip((mean_uv[:, 0] * width).astype(np.int64), 0, width - 1)
    rows = np.clip(((1.0 - mean_uv[:, 1]) * height).astype(np.int64), 0, height - 1)
    return texture[rows, cols]


def segment(mesh, texture: np.ndarray, k: int = 2) -> np.ndarray:
    """Cluster the mesh's faces by baked colour into ``k`` groups → per-face labels.

    Colours are compared in **CIELAB** (perceptual distance, not raw RGB), so lit
    and shadowed wood land closer than wood and fabric. Mesh-agnostic: it reads only
    UVs + texture, blind to whether ``mesh`` is the Source or the cut. The fixed
    ``random_state`` keeps the labels deterministic for a given input.
    """
    return _cluster(face_colours(mesh, texture), k)


def _cluster(colours: np.ndarray, k: int) -> np.ndarray:
    """k-means in CIELAB over an ``(n, 3)`` RGB array → an ``(n,)`` cluster label per
    row. The fixed ``random_state`` makes the labels deterministic."""
    lab = rgb2lab(colours.reshape(-1, 1, 3).astype(np.float64) / 255.0).reshape(-1, 3)
    kmeans = KMeans(n_clusters=k, n_init=10, random_state=0)
    return kmeans.fit_predict(lab).astype(np.int32)


def colour_clusters(mesh, texture: np.ndarray, scope_faces: np.ndarray, k: int) -> np.ndarray:
    """k-means labels (0…k−1) for just ``scope_faces`` — the heavy compute, no
    partition mutation. Split out of :func:`split_by_colour` so a caller can run it
    on a worker thread and apply the relabel on the GUI thread (#29 cluster off-thread).
    """
    return _cluster(face_colours(mesh, texture)[scope_faces], k)


def apply_clusters(
    partition: Partition,
    scope: int,
    scope_faces: np.ndarray,
    clusters: np.ndarray,
    k: int,
) -> list[int]:
    """Write ``clusters`` (the labels :func:`colour_clusters` produced) into
    ``partition`` as ``k`` new Parts, leaving every other Part untouched, and drop the
    emptied scope. Mutation only — cheap, and must run on the GUI thread so it never
    races the outliner / buffer reads. Returns the new Part ids.
    """
    new_ids = []
    for c in range(k):
        part_id = partition.create_part(name=f"Part {len(partition.parts) - 1}")
        partition.assign(scope_faces[clusters == c], part_id)
        new_ids.append(part_id)

    # Subdividing a user Part replaces it with its k clusters; Unassigned is the
    # permanent remainder and simply empties.
    if scope != UNASSIGNED_ID:
        partition.delete(scope)
    return new_ids


def split_by_colour(
    partition: Partition,
    mesh,
    texture: np.ndarray,
    k: int = 2,
    scope: int = UNASSIGNED_ID,
) -> list[int]:
    """Cluster only the faces ``scope`` owns into ``k`` new Parts, leaving every other
    Part untouched. Writes through :meth:`Partition.assign`, so the partition stays
    exhaustive and non-overlapping. Returns the new Part ids. The synchronous
    compute-then-apply; the off-thread path calls the two halves separately.
    """
    scope_faces = np.where(partition.labels == scope)[0]
    if scope_faces.size == 0:  # nothing to carve (e.g. everything already assigned)
        return []
    clusters = colour_clusters(mesh, texture, scope_faces, k)
    return apply_clusters(partition, scope, scope_faces, clusters, k)
