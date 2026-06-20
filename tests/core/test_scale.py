"""Scale + units — sizing a Source model for SketchUp (no up-axis control)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

import trimesh

from polycut.core import export_collada, scale_factor, scale_geometry
from polycut.core.model import SourceModel
from polycut.core.scale import detect_source_unit


def _extents(geometry):
    lo, hi = geometry.bounds
    return hi - lo


def test_scale_geometry_scales_bounding_box(box_model):
    """A scale factor multiplies the model's bounding-box dimensions."""
    result = scale_geometry(box_model, 2.0)

    assert np.allclose(_extents(result.geometry), _extents(box_model.geometry) * 2.0)
    assert result.face_count == box_model.face_count  # scaling keeps topology


def test_scale_factor_converts_units():
    """Source/target units produce the right ratio; the multiplier rides on top."""
    assert scale_factor(1.0, "m", "m") == 1.0
    assert scale_factor(2.0, "m", "m") == 2.0
    assert scale_factor(1.0, "m", "cm") == 100.0
    assert scale_factor(1.0, "cm", "m") == pytest.approx(0.01)
    assert scale_factor(1.0, "in", "mm") == pytest.approx(25.4)


def test_scale_keeps_precomputed_normals(box_model):
    """Scaling carries normals across so a heavy export needn't recompute them.

    Decimated meshes ship their normals (the export reads them directly); if a
    scale dropped that cache the export would fall back to a slow recompute.
    """
    from pathlib import Path

    box = box_model.geometry
    mesh = trimesh.Trimesh(
        vertices=box.vertices, faces=box.faces, vertex_normals=box.vertex_normals,
        process=False,
    )
    model = SourceModel(Path("box.obj"), mesh, mesh.faces.shape[0], 1, ())
    before = mesh.vertex_normals.copy()

    scaled = scale_geometry(model, 3.0)

    assert "vertex_normals" in scaled.geometry._cache  # not dropped → export stays cheap
    assert np.allclose(scaled.geometry.vertex_normals, before)  # unit normals unchanged


def _sized_box_model(largest_extent):
    """A box whose largest dimension is ``largest_extent`` — for unit detection."""
    box = trimesh.creation.box(extents=(largest_extent, largest_extent / 2, 0.1))
    return SourceModel(Path("box.obj"), box, int(box.faces.shape[0]), 1, ())


def test_detect_reads_furniture_sized_geometry_as_meters():
    """A model a couple of metres across reads as metres — Meshy's native scale."""
    assert detect_source_unit(_sized_box_model(1.9)) == "m"


def test_detect_reads_millimetre_scaled_geometry_as_mm():
    """The same couch authored at ×1000 reads as millimetres, not metres."""
    assert detect_source_unit(_sized_box_model(1900.0)) == "mm"


@pytest.mark.slow
def test_detect_reads_the_meshy_sofa_as_meters(sofa_model):
    """The real Meshy fixture (the known case the AC names) detects as metres."""
    assert detect_source_unit(sofa_model) == "m"


def test_scale_uses_the_meshs_cached_normals_not_a_recompute():
    """Scaling must read the loaded mesh's own (cached) normals, not recompute them
    from a fresh copy — a recompute on the 646k sofa is a multi-second scipy-fallback
    grind at export. A uniform scale leaves normals untouched, so a deliberately
    non-geometric cached normal (+X on an XY quad) must survive verbatim."""
    quad = trimesh.Trimesh(
        vertices=np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=float),
        faces=np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64),
        vertex_normals=np.tile([1.0, 0.0, 0.0], (4, 1)),  # bogus: +X, not the +Z face normal
        process=False,
    )
    model = SourceModel(Path("quad.obj"), quad, 2, 1, ())

    scaled = scale_geometry(model, 2.0)

    assert np.allclose(scaled.geometry.vertex_normals, [1.0, 0.0, 0.0])


def test_scaled_export_declares_target_unit(box_model, tmp_path):
    """The exported .dae declares the target unit so SketchUp sizes it right."""
    scaled = scale_geometry(box_model, scale_factor(1.0, "m", "cm"))  # ×100
    out = tmp_path / "box.dae"

    export_collada(scaled, out, unit_name="centimeter", unit_meters=0.01)

    text = out.read_text(errors="ignore")
    assert 'name="centimeter"' in text
    assert 'meter="0.01"' in text
