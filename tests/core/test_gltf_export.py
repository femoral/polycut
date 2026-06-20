"""glTF/GLB export — a scene of per-Part submeshes, each its own material + texture.

MVP-4 slice G (ADR-0007): ``export_gltf`` writes a ``.glb`` (or ``.gltf``) where
each non-empty Part is one named submesh with its own embedded texture, so the file
is a single self-contained set of named, material-slotted pieces. Single-texture /
single-Part models degrade to one mesh + one material. Pure headless ``core`` —
these tests build a small model + a hand-made partition and reload the written file.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import trimesh
from PIL import Image

from polycut.core.export import export_gltf
from polycut.core.model import SourceModel
from polycut.core.parts import Partition
from polycut.core.segment import split_by_colour


def _image_colour(geom) -> tuple | None:
    """The solid colour of a reloaded submesh's embedded texture (top-left texel)."""
    material = getattr(geom.visual, "material", None)
    image = getattr(material, "baseColorTexture", None) or getattr(material, "image", None)
    return tuple(int(c) for c in np.asarray(image.convert("RGB"))[0, 0]) if image else None


def _two_texture_model(directory: Path, n_faces: int = 4) -> SourceModel:
    """A model with two distinct source textures (frame red, cushion blue)."""
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
    """Split the faces between two textured Parts (material 0 / material 1)."""
    half = model.face_count // 2
    face_materials = np.array([0] * half + [1] * (model.face_count - half))
    return Partition.from_materials(face_materials, ["frame", "cushion"], [0, 1])


def test_glb_export_writes_one_submesh_per_non_empty_part(tmp_path):
    """A carved model writes a .glb that reloads as a Scene of one named submesh per
    non-empty Part."""
    model = _two_texture_model(tmp_path, n_faces=4)
    partition = _two_part_partition(model)
    out = tmp_path / "out.glb"

    export_gltf(model, out, partition=partition)

    reloaded = trimesh.load(out, process=False)
    assert isinstance(reloaded, trimesh.Scene)
    assert len(reloaded.geometry) == 2


def test_multi_texture_glb_embeds_each_parts_own_texture(tmp_path):
    """Each Part's texture is embedded; reloading recovers both materials, each piece
    keeping its own image (frame red, cushion blue) — a self-contained .glb."""
    model = _two_texture_model(tmp_path, n_faces=4)
    partition = _two_part_partition(model)
    out = tmp_path / "out.glb"

    result = export_gltf(model, out, partition=partition)

    assert result.texture_count == 2
    reloaded = trimesh.load(out, process=False)
    colours = {_image_colour(g) for g in reloaded.geometry.values()}
    assert (200, 40, 40) in colours and (40, 40, 200) in colours


def test_glb_triangles_cover_every_face_exactly_once(tmp_path):
    """The partition is exhaustive, so the submesh triangles sum to the mesh face
    count — no face dropped or duplicated across submeshes."""
    model = _two_texture_model(tmp_path, n_faces=6)
    partition = _two_part_partition(model)
    out = tmp_path / "out.glb"

    export_gltf(model, out, partition=partition)

    reloaded = trimesh.load(out, process=False)
    total = sum(len(g.faces) for g in reloaded.geometry.values())
    assert total == model.face_count


def test_gltf_text_format_is_supported(tmp_path):
    """The same content writes to a ``.gltf`` (text + buffers) and reloads as a Scene
    of the per-Part submeshes."""
    model = _two_texture_model(tmp_path, n_faces=4)
    partition = _two_part_partition(model)
    out = tmp_path / "out.gltf"

    export_gltf(model, out, partition=partition)

    assert out.exists()
    reloaded = trimesh.load(out, process=False)
    assert isinstance(reloaded, trimesh.Scene)
    assert len(reloaded.geometry) == 2


def test_single_part_model_exports_as_one_mesh_and_material(tmp_path):
    """With no Parts carved the model exports as a single textured mesh — parity with
    the single-Part case."""
    tex = tmp_path / "bake.png"
    Image.new("RGB", (4, 4), (180, 120, 60)).save(tex)
    mesh = trimesh.Trimesh(
        vertices=np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], float),
        faces=np.array([[0, 1, 2]], np.int64),
        visual=trimesh.visual.TextureVisuals(uv=np.zeros((3, 2))),
        process=False,
    )
    model = SourceModel(
        source_path=tmp_path / "m.glb", geometry=mesh, face_count=1,
        object_count=1, textures=(tex,),
    )
    out = tmp_path / "out.glb"

    result = export_gltf(model, out)  # no partition

    assert result.texture_count == 1
    reloaded = trimesh.load(out, process=False)
    geoms = reloaded.geometry if isinstance(reloaded, trimesh.Scene) else {"_": reloaded}
    assert len(geoms) == 1


@pytest.mark.slow
def test_glb_export_on_the_real_sofa(simplified_sofa, sofa_model, tmp_path):
    """End-to-end on the 646k Meshy sofa: split by material, export .glb, and it
    reloads as named submeshes whose triangles still cover the whole simplified mesh."""
    model = simplified_sofa[0]
    mesh = model.geometry
    texture = np.asarray(Image.open(sofa_model.texture_path).convert("RGB"))
    partition = Partition.fresh(face_count=int(mesh.faces.shape[0]))
    split_by_colour(partition, mesh, texture, k=2)
    out = tmp_path / "sofa.glb"

    export_gltf(model, out, partition=partition)

    reloaded = trimesh.load(out, process=False)
    assert isinstance(reloaded, trimesh.Scene)
    total = sum(len(g.faces) for g in reloaded.geometry.values())
    assert total == int(mesh.faces.shape[0])
