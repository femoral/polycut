"""Multi-Part Collada export — N named groups, each its own material slot (#22).

The MVP-3 payoff (shape B, ADR-0004/0001): the partition is written so SketchUp
sees one named group per Part, each carrying a distinct, swappable material slot,
all sharing the single baked texture (one ``<library_images>`` entry). Pure
headless ``core``. These tests build a small textured model + a hand-made
partition (slice B not required) and assert on the emitted Collada document.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import trimesh
from collada import Collada
from PIL import Image

from polycut.core.export import export_collada
from polycut.core.model import SourceModel
from polycut.core.parts import Partition
from polycut.core.segment import split_by_colour


def _textured_model(directory: Path, n_faces: int = 4) -> SourceModel:
    """A tiny textured model on disk: ``n_faces`` independent triangles with UVs and
    a real (small) PNG beside it, so the export can copy + reference the texture."""
    texture_path = directory / "bake.png"
    Image.new("RGB", (4, 4), (180, 120, 60)).save(texture_path)

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
        source_path=directory / "model.obj",
        geometry=mesh,
        face_count=n_faces,
        object_count=1,
        textures=(texture_path,),
    )


def _two_part_partition(face_count: int) -> Partition:
    """Split the faces in half between two named Parts."""
    partition = Partition.fresh(face_count=face_count)
    frame = partition.create_part(name="frame")
    cushions = partition.create_part(name="cushions")
    half = face_count // 2
    partition.assign(np.arange(0, half), frame)
    partition.assign(np.arange(half, face_count), cushions)
    return partition


def test_export_writes_one_named_group_and_slot_per_part(tmp_path):
    """Two Parts export as two <geometry> + two Part-named <material>, all sharing a
    single <library_images> entry — N selectable groups, N swappable slots."""
    model = _textured_model(tmp_path, n_faces=4)
    partition = _two_part_partition(model.face_count)
    out = tmp_path / "out.dae"

    export_collada(model, out, partition=partition)

    doc = Collada(str(out))
    assert len(doc.geometries) == 2
    assert len(doc.images) == 1  # one baked texture, shared
    assert {m.name for m in doc.materials} == {"frame", "cushions"}


def _exported_triangle_count(doc) -> int:
    return sum(len(prim) for geom in doc.geometries for prim in geom.primitives)


def test_exported_triangles_cover_every_face_exactly_once(tmp_path):
    """The partition is exhaustive, so the exported triangles across all groups sum to
    the mesh face count — no face dropped, none duplicated."""
    model = _textured_model(tmp_path, n_faces=6)
    partition = _two_part_partition(model.face_count)
    out = tmp_path / "out.dae"

    export_collada(model, out, partition=partition)

    doc = Collada(str(out))
    assert _exported_triangle_count(doc) == model.face_count


def test_single_part_model_exports_as_one_group(tmp_path):
    """With no Parts carved (everything Unassigned) the model exports as a single
    valid group — parity with the pre-Parts single-mesh writer."""
    model = _textured_model(tmp_path, n_faces=4)
    out = tmp_path / "out.dae"

    export_collada(model, out)  # no partition

    doc = Collada(str(out))
    assert len(doc.geometries) == 1
    assert _exported_triangle_count(doc) == model.face_count
    assert len(doc.images) == 1


def test_unassigned_exports_as_its_own_slot_when_non_empty(tmp_path):
    """A partially-carved model exports the leftover faces as their own Unassigned
    slot, so the export still covers 100% of the geometry."""
    model = _textured_model(tmp_path, n_faces=6)
    partition = Partition.fresh(face_count=6)
    frame = partition.create_part(name="frame")
    partition.assign([0, 1, 2], frame)  # leaves faces 3,4,5 in Unassigned
    out = tmp_path / "out.dae"

    export_collada(model, out, partition=partition)

    doc = Collada(str(out))
    assert {m.name for m in doc.materials} == {"frame", "Unassigned"}
    assert _exported_triangle_count(doc) == 6


def test_texture_is_copied_beside_output_and_referenced_relatively(tmp_path):
    """The one shared texture is copied next to the .dae and referenced by relative
    name, so the export is self-contained and portable."""
    model = _textured_model(tmp_path, n_faces=4)
    partition = _two_part_partition(model.face_count)
    out = tmp_path / "sub" / "out.dae"

    export_collada(model, out, partition=partition)

    assert (out.parent / "bake.png").exists()       # copied beside the output
    doc = Collada(str(out))
    assert doc.images[0].path == "bake.png"          # relative, no absolute path leaked


@pytest.mark.slow
def test_split_sofa_exports_named_groups_covering_every_face(simplified_sofa, tmp_path):
    """End-to-end on the real sofa: split by material, export, and the .dae reloads as
    N named groups whose triangles still cover 100% of the simplified mesh."""
    model = simplified_sofa[0]
    mesh = model.geometry
    texture = np.asarray(Image.open(model.texture_path).convert("RGB"))
    partition = Partition.fresh(face_count=int(mesh.faces.shape[0]))
    split_by_colour(partition, mesh, texture, k=2)
    out = tmp_path / "sofa.dae"

    export_collada(model, out, partition=partition)

    doc = Collada(str(out))
    assert len(doc.geometries) == 2  # wood + fabric, Unassigned empty so omitted
    assert _exported_triangle_count(doc) == int(mesh.faces.shape[0])
    reloaded = trimesh.load(out, process=False)
    assert isinstance(reloaded, trimesh.Scene)
    assert (model.texture_path.name and (out.parent / model.texture_path.name).exists())
