"""Simplify — texture-preserving decimation of a Source model (ADR-0002)."""

from __future__ import annotations

import pytest
import trimesh

from polycut.core import export_collada


@pytest.mark.slow
def test_simplify_reduces_to_target(simplified_sofa, sofa_model):
    """Decimation lands the face count on the requested target (within tol)."""
    result, target = simplified_sofa

    assert result.face_count < sofa_model.face_count
    assert abs(result.face_count - target) <= target * 0.02


@pytest.mark.slow
def test_simplify_preserves_texture_coordinates(simplified_sofa, sofa_model):
    """UVs survive the collapse and the baked texture is carried over intact."""
    result, _target = simplified_sofa

    uv = result.geometry.visual.uv
    assert uv is not None
    assert len(uv) == len(result.geometry.vertices)
    assert uv.min() >= 0.0 and uv.max() <= 1.0

    assert result.has_texture is True
    assert result.texture_path == sofa_model.texture_path


@pytest.mark.slow
def test_simplified_model_exports_textured_and_reduced(simplified_sofa, tmp_path):
    """A simplified model exports to a textured .dae carrying the reduced count."""
    result, target = simplified_sofa
    out = tmp_path / "sofa_simplified.dae"

    export_result = export_collada(result, out)

    assert export_result.texture_count == 1
    assert (out.parent / result.texture_path.name).exists()

    reloaded = trimesh.load(out, process=False)
    reloaded_faces = sum(int(m.faces.shape[0]) for m in reloaded.geometry.values())
    assert abs(reloaded_faces - target) <= target * 0.02
