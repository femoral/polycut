"""Turn a loaded model into the buffers the Qt3D viewport uploads (#8).

The viewport renders the *current* geometry — the same faithful mesh the
exporter writes. This module is the no-Qt seam between that geometry and the
GPU: it interleaves positions/normals/UVs into one vertex buffer and emits the
triangle index buffer, so the QML ``QQuick3DGeometry`` is dumb plumbing and the
translation stays unit-testable. No Qt import lives here.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import trimesh

from polycut.core.parts import UNASSIGNED_COLOUR, UNASSIGNED_ID

# How far the active Part's colour is pushed toward white as the selection highlight.
_HIGHLIGHT = 0.4


@dataclass(frozen=True)
class MeshBuffers:
    """GPU-ready buffers for one mesh.

    ``vertex_data`` is the interleaved per-vertex attribute buffer (float32);
    ``stride`` is its bytes-per-vertex. The renderer uploads these verbatim.
    """

    vertex_count: int
    triangle_count: int
    vertex_data: bytes
    index_data: bytes
    line_index_data: bytes  # unique triangle edges, for the Wireframe / Edges modes
    line_count: int
    stride: int
    bounds_min: tuple[float, float, float]
    bounds_max: tuple[float, float, float]


def build_mesh_buffers(model) -> MeshBuffers:
    """Build the render buffers for ``model``'s current geometry.

    A multi-object model loads as a ``trimesh.Scene``; the viewport draws the
    whole model as one mesh, so the scene is fused into a single ``Trimesh``
    first (every geometry's triangles, not just the first).
    """
    geometry = model.geometry
    if isinstance(geometry, trimesh.Scene):
        geometry = _fuse_scene(geometry)

    positions = np.asarray(geometry.vertices, dtype=np.float32)
    normals = np.asarray(geometry.vertex_normals, dtype=np.float32)
    uv = _vertex_uv(geometry, len(positions))
    interleaved = np.hstack([positions, normals, uv])
    vertex_data = np.ascontiguousarray(interleaved).tobytes()

    indices = np.asarray(geometry.faces, dtype=np.uint32)
    index_data = np.ascontiguousarray(indices).tobytes()

    edges = _unique_edges(indices)
    line_index_data = np.ascontiguousarray(edges).tobytes()

    lo = positions.min(axis=0)
    hi = positions.max(axis=0)

    return MeshBuffers(
        vertex_count=len(geometry.vertices),
        triangle_count=int(geometry.faces.shape[0]),
        vertex_data=vertex_data,
        index_data=index_data,
        line_index_data=line_index_data,
        line_count=int(edges.shape[0]),
        stride=interleaved.shape[1] * 4,
        bounds_min=(float(lo[0]), float(lo[1]), float(lo[2])),
        bounds_max=(float(hi[0]), float(hi[1]), float(hi[2])),
    )


@dataclass(frozen=True)
class PartBuffers:
    """GPU buffers for the flat-colour Parts view.

    ``vertex_data`` interleaves position (3 floats) + Part RGBA (4 floats) per
    vertex — no normals/UVs, since the view is flat and unlit. Shares the mesh's
    triangle indices.
    """

    vertex_count: int
    triangle_count: int
    vertex_data: bytes
    index_data: bytes
    stride: int
    bounds_min: tuple[float, float, float]
    bounds_max: tuple[float, float, float]


def build_part_buffers(mesh, partition, active_id: int = UNASSIGNED_ID) -> PartBuffers:
    """Build the flat-colour Parts buffers for ``mesh`` under ``partition``.

    Positions come straight from the (simplified) mesh — the exact geometry the
    exporter writes — interleaved with each vertex's Part colour
    (:func:`build_part_colours`), with ``active_id`` brightened as the selection
    highlight. Re-run whenever a carve or the selection changes.
    """
    positions = np.asarray(mesh.vertices, dtype=np.float32)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    colours = build_part_colours(partition, faces, len(positions), active_id)
    interleaved = np.ascontiguousarray(np.hstack([positions, colours]), dtype=np.float32)
    indices = np.ascontiguousarray(np.asarray(mesh.faces, dtype=np.uint32))
    lo = positions.min(axis=0)
    hi = positions.max(axis=0)
    return PartBuffers(
        vertex_count=len(positions),
        triangle_count=int(faces.shape[0]),
        vertex_data=interleaved.tobytes(),
        index_data=indices.tobytes(),
        stride=interleaved.shape[1] * 4,
        bounds_min=(float(lo[0]), float(lo[1]), float(lo[2])),
        bounds_max=(float(hi[0]), float(hi[1]), float(hi[2])),
    )


def build_part_colours(
    partition, faces: np.ndarray, vertex_count: int, active_id: int = UNASSIGNED_ID
) -> np.ndarray:
    """Per-vertex RGBA (float32, 0–1) painting each face in its Part's colour.

    The flat-colour Parts view reuses the existing indexed vertex buffer, so the
    colour is per-vertex: every face scatters its Part's swatch colour onto its
    three vertices. Faces still in Unassigned take the neutral remainder grey. A
    hidden Part drops to zero alpha (the view discards it); the ``active_id`` Part,
    when a real Part is selected, brightens toward white as the selection highlight.
    """
    faces = np.asarray(faces, dtype=np.int64)
    labels = np.asarray(partition.labels)
    colours = np.empty((vertex_count, 4), dtype=np.float32)
    colours[:, :3] = np.asarray(UNASSIGNED_COLOUR, dtype=np.float32) / 255.0
    colours[:, 3] = 1.0
    for part in partition.parts:
        rgb = np.asarray(part.colour, dtype=np.float32) / 255.0
        verts = np.unique(faces[labels == part.id])  # vertices the Part's faces touch
        colours[verts, :3] = rgb
        colours[verts, 3] = 1.0 if part.visible else 0.0  # hidden Part → blend away
    if active_id != UNASSIGNED_ID and active_id in {p.id for p in partition.parts}:
        verts = np.unique(faces[labels == active_id])
        colours[verts, :3] += (1.0 - colours[verts, :3]) * _HIGHLIGHT
    return colours


def _fuse_scene(scene: "trimesh.Scene"):
    """Fuse a multi-geometry scene into one ``Trimesh`` for the viewport.

    ``Scene.to_geometry`` concatenates the parts but drops their vertex normals, so
    accessing the fused mesh's normals would recompute them — a path that needs
    scipy (which we don't ship) and prints a noisy fallback. Concatenation keeps
    vertex order, so the parts already carry the right normals (read straight from
    the OBJ); we stack them back onto the fused mesh to keep the fast, quiet path.
    """
    parts = list(scene.geometry.values())
    fused = scene.to_geometry()
    normals = np.vstack([p.vertex_normals for p in parts])
    if len(normals) == len(fused.vertices):  # no vertices were merged on fuse
        fused.vertex_normals = normals
    return fused


def _unique_edges(faces: np.ndarray) -> np.ndarray:
    """The mesh's triangle edges as unique low→high vertex-index pairs.

    Each triangle contributes its three edges; edges shared between adjacent
    triangles are collapsed to one (so a quad's diagonal is drawn once, not twice).
    Ordering each pair low→high makes (a,b) and (b,a) the same edge before dedup.
    """
    tri = faces.reshape(-1, 3)
    edges = np.concatenate([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]])
    edges = np.sort(edges, axis=1)  # canonical orientation so shared edges match
    return np.unique(edges, axis=0).astype(np.uint32)


def _vertex_uv(geometry, vertex_count) -> np.ndarray:
    """Per-vertex UVs, or zeros when the mesh carries none (missing-texture case).

    The interleaved layout stays fixed whether or not a texture is present, so the
    renderer's vertex format never changes — only the material drops the sampler.
    """
    uv = getattr(geometry.visual, "uv", None)
    if uv is None:
        return np.zeros((vertex_count, 2), dtype=np.float32)
    return np.asarray(uv, dtype=np.float32)
