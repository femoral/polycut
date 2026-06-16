"""Preview == export at the core seam (#10).

The before/after split must show the *exact* mesh the exporter writes — not a
separate preview-quality cut (ADR-0003). Both the viewport buffers and the
Collada export consume the same ``SourceModel.geometry``; this pins that
contract at the headless core seam: the triangles you preview are the faces you
export, for the same model.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh

from polycut.core import build_mesh_buffers, export_collada
from polycut.core.model import SourceModel


def _model(path):
    """A small textured mesh standing in for a simplified result."""
    vertices = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=np.float64)
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
    return SourceModel(
        source_path=Path(path),
        geometry=mesh,
        face_count=2,
        object_count=1,
        texture_path=None,
    )


def test_previewed_triangles_equal_exported_faces(tmp_path):
    """The triangle count the viewport draws matches the face count the exporter
    writes for the same model — preview mesh == export mesh."""
    model = _model("a.obj")

    buffers = build_mesh_buffers(model)
    result = export_collada(model, tmp_path / "a.dae")

    assert buffers.triangle_count == result.face_count
