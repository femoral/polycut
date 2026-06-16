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
    stride: int
    bounds_min: tuple[float, float, float]
    bounds_max: tuple[float, float, float]


def build_mesh_buffers(model) -> MeshBuffers:
    """Build the render buffers for ``model``'s current geometry."""
    geometry = model.geometry

    positions = np.asarray(geometry.vertices, dtype=np.float32)
    normals = np.asarray(geometry.vertex_normals, dtype=np.float32)
    uv = _vertex_uv(geometry, len(positions))
    interleaved = np.hstack([positions, normals, uv])
    vertex_data = np.ascontiguousarray(interleaved).tobytes()

    indices = np.asarray(geometry.faces, dtype=np.uint32)
    index_data = np.ascontiguousarray(indices).tobytes()

    lo = positions.min(axis=0)
    hi = positions.max(axis=0)

    return MeshBuffers(
        vertex_count=len(geometry.vertices),
        triangle_count=int(geometry.faces.shape[0]),
        vertex_data=vertex_data,
        index_data=index_data,
        stride=interleaved.shape[1] * 4,
        bounds_min=(float(lo[0]), float(lo[1]), float(lo[2])),
        bounds_max=(float(hi[0]), float(hi[1]), float(hi[2])),
    )


def _vertex_uv(geometry, vertex_count) -> np.ndarray:
    """Per-vertex UVs, or zeros when the mesh carries none (missing-texture case).

    The interleaved layout stays fixed whether or not a texture is present, so the
    renderer's vertex format never changes — only the material drops the sampler.
    """
    uv = getattr(geometry.visual, "uv", None)
    if uv is None:
        return np.zeros((vertex_count, 2), dtype=np.float32)
    return np.asarray(uv, dtype=np.float32)
