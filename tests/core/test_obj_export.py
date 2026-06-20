"""OBJ export — per-Part ``g`` group + ``usemtl``, a shared ``.mtl``, multi-texture.

MVP-4 slice H (ADR-0007): ``export_obj`` writes one ``.obj`` with a ``g`` group and
``usemtl`` per non-empty Part, a sibling ``.mtl`` declaring N materials (each its own
``map_Kd``), and the textures copied beside the output — so an older tool that reads
OBJ still receives the split. Single-texture / single-Part models degrade to one
group + one material. Pure headless ``core``; these tests reload the written file
and read the ``.mtl`` text.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import trimesh
from PIL import Image

from polycut.core.export import export_obj
from polycut.core.model import SourceModel
from polycut.core.parts import Partition
from polycut.core.segment import split_by_colour


def _two_texture_model(directory: Path, n_faces: int = 4) -> SourceModel:
    t0 = directory / "frame.png"
    Image.new("RGB", (4, 4), (200, 40, 40)).save(t0)
    t1 = directory / "cushion.png"
    Image.new("RGB", (4, 4), (40, 40, 200)).save(t1)

    verts, faces, uv = [], [], []
    for i in range(n_faces):
        base = 3 * i
        verts += [[i, 0, 0], [i + 1, 0, 0], [i, 1, 0]]
        faces.append([base, base + 1, base + 2])
        uv += [[0.5, 0.5]] * 3
    mesh = trimesh.Trimesh(
        vertices=np.array(verts, float),
        faces=np.array(faces, np.int64),
        visual=trimesh.visual.TextureVisuals(uv=np.array(uv)),
        process=False,
    )
    return SourceModel(
        source_path=directory / "model.glb",
        geometry=mesh,
        face_count=n_faces,
        object_count=2,
        textures=(t0, t1),
    )


def _two_part_partition(model: SourceModel) -> Partition:
    half = model.face_count // 2
    face_materials = np.array([0] * half + [1] * (model.face_count - half))
    return Partition.from_materials(face_materials, ["frame", "cushion"], [0, 1])


def _image_colour(geom) -> tuple | None:
    """The solid colour of a reloaded group's texture (top-left texel)."""
    material = getattr(geom.visual, "material", None)
    image = getattr(material, "baseColorTexture", None) or getattr(material, "image", None)
    return tuple(int(c) for c in np.asarray(image.convert("RGB"))[0, 0]) if image else None


def test_obj_export_writes_a_group_and_usemtl_per_part(tmp_path):
    """A carved model writes a .obj with one ``g`` group + ``usemtl`` per non-empty
    Part and a sibling .mtl, reloading as a Scene of those groups."""
    model = _two_texture_model(tmp_path, n_faces=4)
    partition = _two_part_partition(model)
    out = tmp_path / "out.obj"

    export_obj(model, out, partition=partition)

    assert out.exists()
    assert out.with_suffix(".mtl").exists()
    text = out.read_text()
    assert text.count("\ng ") == 2  # two named groups (file starts with mtllib)
    assert text.count("usemtl ") == 2
    reloaded = trimesh.load(out, process=False)
    assert isinstance(reloaded, trimesh.Scene)
    assert len(reloaded.geometry) == 2


def test_multi_texture_obj_writes_n_materials_each_its_own_map_kd(tmp_path):
    """A multi-textured model writes N materials in the .mtl, each map_Kd pointing at
    its own copied texture by relative name (no absolute path) — and reloading
    recovers each Part's own image."""
    model = _two_texture_model(tmp_path, n_faces=4)
    partition = _two_part_partition(model)
    out = tmp_path / "out.obj"

    result = export_obj(model, out, partition=partition)

    assert result.texture_count == 2
    mtl = out.with_suffix(".mtl").read_text()
    assert mtl.count("newmtl ") == 2
    map_kds = [line.split(maxsplit=1)[1] for line in mtl.splitlines() if line.startswith("map_Kd ")]
    assert sorted(map_kds) == ["cushion.png", "frame.png"]
    assert all("/" not in name and "\\" not in name for name in map_kds)  # relative basenames
    assert (out.parent / "frame.png").exists() and (out.parent / "cushion.png").exists()
    reloaded = trimesh.load(out, process=False)
    colours = {_image_colour(g) for g in reloaded.geometry.values()}
    assert (200, 40, 40) in colours and (40, 40, 200) in colours


def test_obj_triangles_cover_every_face_exactly_once(tmp_path):
    """The partition is exhaustive, so the triangles across all groups sum to the mesh
    face count — no face dropped or duplicated."""
    model = _two_texture_model(tmp_path, n_faces=6)
    partition = _two_part_partition(model)
    out = tmp_path / "out.obj"

    export_obj(model, out, partition=partition)

    reloaded = trimesh.load(out, process=False)
    total = sum(len(g.faces) for g in reloaded.geometry.values())
    assert total == model.face_count


def test_single_part_obj_exports_one_group_and_material(tmp_path):
    """With no Parts carved the model exports as a single group + single material —
    parity with the pre-Parts writer."""
    tex = tmp_path / "bake.png"
    Image.new("RGB", (4, 4), (180, 120, 60)).save(tex)
    mesh = trimesh.Trimesh(
        vertices=np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], float),
        faces=np.array([[0, 1, 2]], np.int64),
        visual=trimesh.visual.TextureVisuals(uv=np.zeros((3, 2))),
        process=False,
    )
    model = SourceModel(
        source_path=tmp_path / "m.obj", geometry=mesh, face_count=1,
        object_count=1, textures=(tex,),
    )
    out = tmp_path / "out.obj"

    result = export_obj(model, out)  # no partition

    assert result.texture_count == 1
    assert out.read_text().count("\ng ") == 1
    assert out.with_suffix(".mtl").read_text().count("newmtl ") == 1


@pytest.mark.slow
def test_obj_export_on_the_real_sofa(simplified_sofa, sofa_model, tmp_path):
    """End-to-end on the 646k Meshy sofa: split by material, export .obj, and it
    reloads as named groups whose triangles still cover the whole simplified mesh."""
    model = simplified_sofa[0]
    mesh = model.geometry
    texture = np.asarray(Image.open(sofa_model.texture_path).convert("RGB"))
    partition = Partition.fresh(face_count=int(mesh.faces.shape[0]))
    split_by_colour(partition, mesh, texture, k=2)
    out = tmp_path / "sofa.obj"

    export_obj(model, out, partition=partition)

    reloaded = trimesh.load(out, process=False)
    assert isinstance(reloaded, trimesh.Scene)
    total = sum(len(g.faces) for g in reloaded.geometry.values())
    assert total == int(mesh.faces.shape[0])
