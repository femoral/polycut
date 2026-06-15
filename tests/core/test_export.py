import pytest
import trimesh


def _face_count(geometry) -> int:
    meshes = (
        list(geometry.geometry.values())
        if isinstance(geometry, trimesh.Scene)
        else [geometry]
    )
    return sum(int(m.faces.shape[0]) for m in meshes)


@pytest.mark.slow
def test_export_dae_roundtrips_geometry(exported_sofa):
    """Pass-through export: the .dae re-loads with the same face count."""
    out, _result, model = exported_sofa

    assert out.exists()
    reloaded = trimesh.load(out, process=False)
    assert _face_count(reloaded) == model.face_count


@pytest.mark.slow
def test_export_copies_and_references_texture(exported_sofa):
    """The .dae references its texture, copied beside it for a portable export."""
    out, result, _model = exported_sofa

    copied = out.parent / "model_baseColor.png"
    assert copied.exists()
    assert result.texture_count == 1
    assert "model_baseColor.png" in out.read_text(errors="ignore")


@pytest.mark.slow
def test_export_result_reports_summary(exported_sofa):
    """The post-export summary fields are populated for the UI to confirm."""
    out, result, model = exported_sofa

    assert result.output_path == out
    assert result.output_size_bytes == out.stat().st_size > 0
    assert result.face_count == model.face_count
    assert result.texture_count == 1
