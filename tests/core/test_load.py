from polycut.core import load_source_model


def test_loads_real_meshy_sofa_stats(sofa_model):
    assert sofa_model.face_count == 646_119
    assert sofa_model.object_count == 1
    assert sofa_model.has_texture is True
    assert sofa_model.texture_path is not None
    assert sofa_model.texture_path.name == "model_baseColor.png"


def test_missing_texture_is_detected(tmp_path):
    """An OBJ whose .mtl/texture didn't travel with it loads with no texture."""
    obj = tmp_path / "bare.obj"
    obj.write_text(
        "mtllib bare.mtl\n"  # references an .mtl that isn't on disk
        "o bare\n"
        "v 0 0 0\nv 1 0 0\nv 0 1 0\n"
        "vt 0 0\nvt 1 0\nvt 0 1\n"
        "f 1/1 2/2 3/3\n"
    )

    model = load_source_model(obj)

    assert model.has_texture is False
    assert model.texture_path is None
