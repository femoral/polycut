from polycut.core import load_source_model


def test_loads_real_meshy_sofa_stats(sofa_model):
    assert sofa_model.face_count == 646_119
    assert sofa_model.object_count == 1
    assert sofa_model.has_texture is True
    assert sofa_model.texture_path is not None
    assert sofa_model.texture_path.name == "model_baseColor.png"


def test_single_object_is_listed_named_by_the_file(tmp_path):
    """A fused single-mesh OBJ surfaces one outliner object named by the file stem
    (Meshy's blob has no useful group name), carrying the model's whole face count."""
    obj = tmp_path / "couch.obj"
    obj.write_text("o blob\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")

    model = load_source_model(obj)

    assert [(o.name, o.face_count) for o in model.objects] == [("couch", 1)]


def test_multi_geometry_model_lists_each_piece_with_its_faces(tmp_path):
    """A model that loads as several geometries (trimesh fuses plain 'o' groups, so
    distinct pieces need distinct materials) lists one outliner row per piece — each
    with its own face count, stem-derived names, summing to the model total."""
    obj = tmp_path / "couch.obj"
    obj.write_text(
        "usemtl a\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n"
        "usemtl b\nv 0 0 1\nv 1 0 1\nv 0 1 1\nv 1 1 1\nf 4 5 6\nf 5 7 6\n"
    )

    model = load_source_model(obj)

    assert model.object_count == 2
    assert [o.name for o in model.objects] == ["couch", "couch.1"]
    assert sorted(o.face_count for o in model.objects) == [1, 2]
    assert sum(o.face_count for o in model.objects) == model.face_count


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
