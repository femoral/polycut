"""Turn a loaded model into the buffers the Qt3D viewport uploads (#8).

The viewport renders the *current* geometry — the same faithful mesh the
exporter writes. This module is the no-Qt seam between that geometry and the
GPU: it interleaves positions/normals/UVs into one vertex buffer and emits the
triangle index buffer, so the QML ``QQuick3DGeometry`` is dumb plumbing and the
translation stays unit-testable. No Qt import lives here.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

import numpy as np
import trimesh

from polycut.core.parts import UNASSIGNED_COLOUR, UNASSIGNED_ID

# How far the active Part's colour is pushed toward white as the selection highlight.
_HIGHLIGHT = 0.4


class Attr(enum.Enum):
    """A vertex attribute kind, in a neutral (Qt-free) vocabulary.

    The buffer describes its own layout in these terms so core stays Qt-free; the
    bridge holds the one small map from these kinds to Qt3D's attribute semantics.
    """

    POSITION = "position"
    NORMAL = "normal"
    TEXCOORD = "texcoord"
    COLOR = "color"


@dataclass(frozen=True)
class VertexAttr:
    """One attribute in an interleaved vertex: its kind, byte offset, and how many
    float32 components it spans."""

    kind: Attr
    offset: int  # byte offset into the interleaved vertex
    components: int  # number of float32 components


def _layout(*specs: tuple[Attr, int]) -> tuple[VertexAttr, ...]:
    """Build a contiguous float32 attribute layout from ordered ``(kind, components)``
    pairs. Offsets accumulate left-to-right, so a layout built from the same order as
    an ``np.hstack`` cannot drift from the interleave it describes — the offsets are
    derived from the same component sizes, never written out by hand."""
    attrs, offset = [], 0
    for kind, components in specs:
        attrs.append(VertexAttr(kind, offset, components))
        offset += components * 4  # float32 == 4 bytes
    return tuple(attrs)


# The interleave each builder produces, as a self-describing layout (built right
# beside the matching np.hstack below, so the offsets can never lie).
_MESH_LAYOUT = _layout((Attr.POSITION, 3), (Attr.NORMAL, 3), (Attr.TEXCOORD, 2))
_PARTS_LAYOUT = _layout((Attr.POSITION, 3), (Attr.COLOR, 4))
_HIGHLIGHT_LAYOUT = _layout((Attr.POSITION, 3))


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
    layout: tuple[VertexAttr, ...] = _MESH_LAYOUT  # self-describing attribute offsets


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
    layout: tuple[VertexAttr, ...] = _PARTS_LAYOUT  # self-describing attribute offsets
    # The flat-colour view has no line pass, but every buffer carries a line field so
    # all four are structurally uniform behind the one geometry adapter (empty here).
    line_index_data: bytes = b""
    line_count: int = 0


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


@dataclass(frozen=True)
class HighlightBuffers:
    """GPU buffers for the active-Part highlight silhouette (#30).

    ``vertex_data`` is position only (3 floats) — the fused mesh's own vertices;
    ``index_data`` holds the active Part's **triangles** (its faces, indexing those
    vertices). An offscreen pass renders these faces flat into a mask, and a
    screen-space edge-detect draws a teal contour around the projected silhouette —
    topology-independent, so it reads as an outline even on the half-disconnected
    Meshy cut where an edge-based outline would just be a wireframe.
    """

    vertex_count: int
    triangle_count: int
    vertex_data: bytes
    index_data: bytes
    stride: int
    bounds_min: tuple[float, float, float]
    bounds_max: tuple[float, float, float]
    layout: tuple[VertexAttr, ...] = _HIGHLIGHT_LAYOUT  # self-describing attribute offsets
    # No line pass (it draws filled faces into a mask), but carries a line field so all
    # four buffers are structurally uniform behind the one geometry adapter (empty here).
    line_index_data: bytes = b""
    line_count: int = 0


def build_highlight_buffers(mesh, face_ids) -> HighlightBuffers:
    """Build the silhouette buffers for ``face_ids`` over ``mesh``.

    Positions are the fused mesh's own vertices (full, shared); the index buffer is
    just the active Part's faces, so the offscreen pass draws exactly that Part's
    surface. Only a face-index slice — no edge enumeration — so it stays cheap to
    rebuild on every selection. Rebuilt whenever the active Part or its faces change.
    """
    positions = np.asarray(mesh.vertices, dtype=np.float32)
    tris = np.asarray(mesh.faces, dtype=np.uint32)[np.asarray(face_ids, dtype=np.int64)]
    lo = positions.min(axis=0)
    hi = positions.max(axis=0)
    return HighlightBuffers(
        vertex_count=len(positions),
        triangle_count=int(tris.shape[0]),
        vertex_data=np.ascontiguousarray(positions).tobytes(),
        index_data=np.ascontiguousarray(tris).tobytes(),
        stride=positions.shape[1] * 4,
        bounds_min=(float(lo[0]), float(lo[1]), float(lo[2])),
        bounds_max=(float(hi[0]), float(hi[1]), float(hi[2])),
    )


@dataclass(frozen=True)
class PartChunk:
    """One Part's explode placement wrapping its upload buffer (#31).

    The explode metadata the viewport's node placement reads — ``part_id``, the swatch
    ``colour``, and the radial ``offset`` (part centroid − model centroid, scaled by the
    live ``amount``; Unassigned's is the zero vector so the remainder stays anchored) —
    wraps a pure ``buffers`` the shared geometry adapter draws. That buffer reuses the
    fused mesh's interleaved positions/normals/UVs (no ``trimesh.submesh`` recompute),
    with triangle + edge indices remapped into the chunk's own compacted vertex range —
    the same shape as a mesh buffer, so a chunk shades exactly like the assembled mesh.
    """

    part_id: int
    colour: tuple[int, int, int]
    offset: tuple[float, float, float]
    buffers: MeshBuffers  # the pure upload buffer the geometry adapter consumes


def build_part_chunks(mesh, partition) -> list[PartChunk]:
    """Decompose ``mesh`` into one :class:`PartChunk` per non-empty Part.

    Built once per carve and cached: the viewport spreads the chunks by translating
    each node by ``offset × amount`` (no per-tick buffer re-upload). Each chunk reuses
    the fused mesh's interleaved positions/normals/UVs — gathered for the Part's own
    vertices, with indices remapped — so the chunks shade exactly like the assembled
    mesh and the dropped-normals-cache slow path is avoided. Unassigned is anchored
    (zero offset); the carved Parts pop radially out of it.
    """
    positions = np.asarray(mesh.vertices, dtype=np.float32)
    normals = np.asarray(mesh.vertex_normals, dtype=np.float32)
    uv = _vertex_uv(mesh, len(positions))
    interleaved = np.ascontiguousarray(np.hstack([positions, normals, uv]), dtype=np.float32)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    centroids = np.asarray(mesh.triangles_center, dtype=np.float64)
    model_centroid = centroids.mean(axis=0)
    stride = interleaved.shape[1] * 4

    chunks: list[PartChunk] = []
    labels = np.asarray(partition.labels)
    for part in partition.parts:
        part_faces = np.where(labels == part.id)[0]
        if part_faces.size == 0:
            continue  # an empty Part draws nothing — no chunk

        tris = faces[part_faces]
        used = np.unique(tris)  # the vertices this Part's faces touch
        remap = np.empty(len(positions), dtype=np.int64)
        remap[used] = np.arange(len(used))
        chunk_vertices = np.ascontiguousarray(interleaved[used])
        chunk_tris = np.ascontiguousarray(remap[tris].astype(np.uint32))
        chunk_edges = _unique_edges(remap[tris])

        if part.id == UNASSIGNED_ID:
            offset = (0.0, 0.0, 0.0)  # the remainder stays put
        else:
            delta = centroids[part_faces].mean(axis=0) - model_centroid
            offset = (float(delta[0]), float(delta[1]), float(delta[2]))

        lo = chunk_vertices[:, :3].min(axis=0)
        hi = chunk_vertices[:, :3].max(axis=0)
        chunks.append(
            PartChunk(
                part_id=part.id,
                colour=tuple(part.colour),
                offset=offset,
                buffers=MeshBuffers(
                    vertex_count=len(used),
                    triangle_count=int(part_faces.shape[0]),
                    vertex_data=chunk_vertices.tobytes(),
                    index_data=chunk_tris.tobytes(),
                    line_index_data=np.ascontiguousarray(chunk_edges).tobytes(),
                    line_count=int(chunk_edges.shape[0]),
                    stride=stride,
                    bounds_min=(float(lo[0]), float(lo[1]), float(lo[2])),
                    bounds_max=(float(hi[0]), float(hi[1]), float(hi[2])),
                ),
            )
        )
    return chunks


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
