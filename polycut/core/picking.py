"""Face picking + the colour wand — manual carving tools, headless `core`.

The bridge turns a screen click + camera into a world-space ray (slice F) and hands
it here; all geometry maths stays in this seam (ADR-0004). :func:`pick_face` does a
ray–mesh intersection and returns the nearest hit face; :func:`colour_wand` grows a
selection from a seed face by baked-texture colour. Selections are written into the
:class:`~polycut.core.parts.Partition` with :func:`add_to_part` /
:func:`subtract_from_part`, so the partition invariant always holds.

Picking is a hand-rolled, vectorised Möller–Trumbore over all faces — at carving
scale (~160k faces, one ray per click) that is a few ms, with no native-lib
dependency. If per-frame picking ever needs a true BVH, swap this one function for
``embreex``; nothing else changes.
"""

from __future__ import annotations

from collections import deque

import numpy as np
from skimage.color import rgb2lab

from polycut.core.parts import UNASSIGNED_ID, Partition
from polycut.core.segment import face_colours

_EPS = 1e-9


def pick_face(mesh, origin, direction) -> int | None:
    """Return the id of the nearest face the ray hits, or ``None`` if it misses.

    ``origin`` / ``direction`` are world-space 3-vectors; ``direction`` need not be
    normalised. Möller–Trumbore is evaluated against every face at once.
    """
    origin = np.asarray(origin, dtype=np.float64)
    direction = np.asarray(direction, dtype=np.float64)
    tris = np.asarray(mesh.triangles, dtype=np.float64)  # (n_faces, 3, 3)

    v0, v1, v2 = tris[:, 0], tris[:, 1], tris[:, 2]
    edge1, edge2 = v1 - v0, v2 - v0
    h = np.cross(direction, edge2)
    det = np.einsum("ij,ij->i", edge1, h)

    parallel = np.abs(det) < _EPS
    inv_det = np.where(parallel, 0.0, 1.0 / np.where(parallel, 1.0, det))

    s = origin - v0
    u = inv_det * np.einsum("ij,ij->i", s, h)
    q = np.cross(s, edge1)
    v = inv_det * np.einsum("ij,ij->i", np.broadcast_to(direction, edge1.shape), q)
    t = inv_det * np.einsum("ij,ij->i", edge2, q)

    hit = ~parallel & (u >= -_EPS) & (v >= -_EPS) & (u + v <= 1 + _EPS) & (t > _EPS)
    if not hit.any():
        return None
    candidates = np.where(hit)[0]
    return int(candidates[np.argmin(t[candidates])])  # nearest hit wins


def screen_ray(cam_pos, forward, up, fov_y: float, px: float, py: float, width: float, height: float):
    """Unproject a screen pixel into a world-space ``(origin, direction)`` ray.

    The bridge hands this the camera (position, forward + up axes, vertical field of
    view in **degrees**) and the click pixel ``(px, py)`` measured from the top-left
    of a ``width × height`` viewport. A pinhole model turns that into the ray
    :func:`pick_face` consumes — origin at the camera, direction normalised. The
    centre pixel shoots straight along ``forward``; pixels off-centre tilt by the
    field of view and the viewport's aspect ratio.
    """
    cam_pos = np.asarray(cam_pos, dtype=np.float64)
    forward = np.asarray(forward, dtype=np.float64)
    forward = forward / np.linalg.norm(forward)
    right = np.cross(forward, np.asarray(up, dtype=np.float64))
    right = right / np.linalg.norm(right)
    true_up = np.cross(right, forward)  # re-orthogonalised; unit since right ⟂ forward

    ndc_x = (px + 0.5) / width * 2.0 - 1.0  # +1 at the right edge
    ndc_y = 1.0 - (py + 0.5) / height * 2.0  # +1 at the top edge (py grows downward)
    half_h = np.tan(np.radians(fov_y) / 2.0)
    half_w = half_h * (width / height)

    direction = forward + ndc_x * half_w * right + ndc_y * half_h * true_up
    return cam_pos, direction / np.linalg.norm(direction)


def colour_wand(mesh, texture, seed: int, threshold: float, mode: str = "local") -> np.ndarray:
    """Grow a face selection from ``seed`` by baked-texture colour.

    A face matches when its colour is within ``threshold`` of the seed's in CIELAB.
    ``"global"`` returns every matching face anywhere (the scattered-pattern case);
    ``"local"`` returns only the contiguous patch reachable from the seed across
    edge-shared faces (a magic-wand "contiguous" select; the soup's gaps keep it on
    the clicked piece).
    """
    lab = rgb2lab(face_colours(mesh, texture).reshape(-1, 1, 3) / 255.0).reshape(-1, 3)
    matches = np.linalg.norm(lab - lab[seed], axis=1) <= threshold

    if mode == "global":
        return np.where(matches)[0]
    return _flood(mesh.face_adjacency, matches, seed)


def _flood(adjacency: np.ndarray, matches: np.ndarray, seed: int) -> np.ndarray:
    """Faces reachable from ``seed`` across edge-shared neighbours that all match —
    a contiguous (magic-wand) selection. Edges to non-matching faces are not crossed,
    and the mesh's disconnected pieces keep the fill on the seed's piece."""
    crossable = adjacency[matches[adjacency[:, 0]] & matches[adjacency[:, 1]]]
    neighbours: dict[int, list[int]] = {}
    for a, b in crossable:
        neighbours.setdefault(int(a), []).append(int(b))
        neighbours.setdefault(int(b), []).append(int(a))

    reached = {seed}
    queue = deque([seed])
    while queue:
        face = queue.popleft()
        for nxt in neighbours.get(face, ()):
            if nxt not in reached:
                reached.add(nxt)
                queue.append(nxt)
    return np.array(sorted(reached), dtype=np.int64)


def add_to_part(partition: Partition, faces, part_id: int) -> None:
    """Add a selection to the active Part — the faces are stolen from their owners."""
    partition.assign(faces, part_id)


def subtract_from_part(partition: Partition, faces, part_id: int) -> None:
    """Remove a selection from the active Part, returning only the faces it actually
    owns to Unassigned; faces belonging to other Parts are left alone."""
    faces = np.asarray(faces, dtype=np.int64)
    owned = faces[partition.labels[faces] == part_id]
    partition.assign(owned, UNASSIGNED_ID)
