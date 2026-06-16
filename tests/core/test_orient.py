"""Up-axis remap — rotating a Source model so the chosen axis points up (#12).

Meshy exports don't share SketchUp's orientation, so the designer picks which
source axis is "up" and the model is rotated upright. World up is the viewport's
Y (Qt3D convention); the rotation is baked into the geometry so the viewport and
the export agree. These tests pin the rotation at the core seam: bounding-box
extents move to the axis we expect, topology and normals survive.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh

from polycut.core.model import SourceModel
from polycut.core.orient import remap_up_axis


def _box_model(extents):
    box = trimesh.creation.box(extents=extents)
    return SourceModel(
        source_path=Path("box.obj"),
        geometry=box,
        face_count=int(box.faces.shape[0]),
        object_count=1,
        texture_path=None,
    )


def _extents(geometry):
    lo, hi = geometry.bounds
    return hi - lo


def test_z_up_brings_the_tall_axis_to_y():
    """Source 'z' up rotates the model so its Z extent becomes the Y extent."""
    model = _box_model((1.0, 2.0, 3.0))  # tall in Z

    result = remap_up_axis(model, "z")

    assert np.allclose(_extents(result.geometry), (1.0, 3.0, 2.0))  # Z→Y


def test_y_up_is_a_no_op():
    """Source 'y' up is the identity — the model is already Y-up, left untouched."""
    model = _box_model((1.0, 2.0, 3.0))

    result = remap_up_axis(model, "y")

    assert np.allclose(_extents(result.geometry), (1.0, 2.0, 3.0))


def test_x_up_brings_the_x_axis_to_y():
    """Source 'x' up rotates the model so its X extent becomes the Y extent."""
    model = _box_model((1.0, 2.0, 3.0))  # widest in Z, X is shortest

    result = remap_up_axis(model, "x")

    assert np.allclose(_extents(result.geometry), (2.0, 1.0, 3.0))  # X→Y


def test_remap_rotates_the_cached_normals():
    """The remap rotates vertex normals with the mesh and keeps them cached, so a
    heavy export reads correctly-oriented normals without a (scipy) recompute.

    A quad facing +Z, remapped from 'z' up, should end up facing +Y.
    """
    quad = trimesh.Trimesh(
        vertices=np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=float),
        faces=np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64),
        vertex_normals=np.tile([0.0, 0.0, 1.0], (4, 1)),
        process=False,
    )
    model = SourceModel(Path("quad.obj"), quad, 2, 1, None)

    result = remap_up_axis(model, "z")

    assert "vertex_normals" in result.geometry._cache  # not dropped → export stays cheap
    assert np.allclose(result.geometry.vertex_normals, [0.0, 1.0, 0.0])  # +Z → +Y


def test_remap_keeps_topology_and_metadata():
    """Rotating only moves vertices — face count, texture and composition carry over."""
    model = SourceModel(
        source_path=Path("box.obj"),
        geometry=trimesh.creation.box(extents=(1.0, 2.0, 3.0)),
        face_count=12,
        object_count=1,
        texture_path=Path("box.png"),
    )

    result = remap_up_axis(model, "z")

    assert result.face_count == 12
    assert int(result.geometry.faces.shape[0]) == 12  # topology untouched
    assert result.texture_path == Path("box.png")
    assert result.object_count == 1
