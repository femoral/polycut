import numpy as np
import trimesh
from PIL import Image

from polycut.core import export_collada, load_source_model
from polycut.core.model import ColourSignal, SourceModel
from polycut.core.parts import Partition


def _two_material_glb(path):
    """A GLB of two textured boxes — two source materials that seed two Parts."""

    def boxmat(colour, shift):
        box = trimesh.creation.box()
        box.apply_translation([shift, 0.0, 0.0])
        box.visual = trimesh.visual.TextureVisuals(
            uv=np.zeros((len(box.vertices), 2)),
            image=Image.new("RGB", (4, 4), colour),
        )
        return box

    scene = trimesh.Scene()
    scene.add_geometry(boxmat((200, 50, 50), 0.0), geom_name="frame")
    scene.add_geometry(boxmat((50, 50, 200), 3.0), geom_name="cushion")
    scene.export(path)


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


# --- Multi-format import (MVP-4 slice B, ADR-0007) -------------------------------
# The loader broadens beyond Meshy OBJ to GLB/glTF, DAE, and geometry-only
# PLY/STL/OFF, inferring the format from the file. A model that arrives split into
# materials opens already separated into Parts; geometry-only files carry no colour
# signal and open as one Unassigned blob.


def test_geometry_only_stl_loads_as_one_blob_with_no_colour_signal(tmp_path):
    """A geometry-only STL (no texture, no vertex colour) loads as a single
    Unassigned blob with colour-signal 'none', so the Auto-cluster is disabled and
    the model is carved only by hand."""
    stl = tmp_path / "block.stl"
    trimesh.creation.box(extents=(1.0, 1.0, 1.0)).export(stl)

    model = load_source_model(stl)

    assert model.has_texture is False
    assert model.colour_signal is ColourSignal.NONE
    assert [p.name for p in model.initial_partition.parts] == ["Unassigned"]
    assert model.initial_partition.face_count(0) == model.face_count


def test_vertex_coloured_ply_loads_with_vertex_colour_signal(tmp_path):
    """A PLY carrying per-vertex colour but no UV texture loads with colour-signal
    'vertex', so the Auto-cluster can still group it by colour with no texture."""
    ply = tmp_path / "blob.ply"
    box = trimesh.creation.box()
    box.visual = trimesh.visual.ColorVisuals(
        box, vertex_colors=np.tile([200, 40, 40, 255], (len(box.vertices), 1))
    )
    box.export(ply)

    model = load_source_model(ply)

    assert model.colour_signal is ColourSignal.VERTEX
    assert model.has_texture is False
    assert [p.name for p in model.initial_partition.parts] == ["Unassigned"]


def test_multi_material_glb_opens_split_into_initial_parts(tmp_path):
    """A GLB with two materials opens already separated into two Parts (one per
    material), with every face owned: the per-Part counts sum to the face count and
    Unassigned holds the unmaterialed remainder (here empty)."""
    glb = tmp_path / "sofa.glb"
    _two_material_glb(glb)

    model = load_source_model(glb)

    partition = model.initial_partition
    user_parts = [p for p in partition.parts if p.id != 0]
    assert len(user_parts) == 2
    assert model.colour_signal is ColourSignal.TEXTURE
    assert sum(partition.face_count(p.id) for p in partition.parts) == model.face_count
    assert partition.face_count(0) == 0  # every face carried a source material


def test_each_glb_part_carries_its_own_texture(tmp_path):
    """Each imported Part references its own image, so a multi-textured model keeps
    every piece's appearance: two materials → two textures → two distinct indices."""
    glb = tmp_path / "sofa.glb"
    _two_material_glb(glb)

    model = load_source_model(glb)

    assert model.texture_count == 2
    user_parts = [p for p in model.initial_partition.parts if p.id != 0]
    assert {p.texture for p in user_parts} == {0, 1}
    for part in user_parts:
        assert model.textures[part.texture].exists()  # the materialised image is real


def test_multi_part_dae_loads_split_into_parts_sharing_one_texture(tmp_path):
    """A DAE carved into two Parts over one baked texture re-loads already split into
    those two Parts, both pointing at the one shared image (deduped to a single
    texture) — a Polycut .dae round-trips back into Polycut."""
    box = trimesh.creation.box()
    box.visual = trimesh.visual.TextureVisuals(
        uv=np.zeros((len(box.vertices), 2)), image=Image.new("RGB", (4, 4), (180, 120, 60))
    )
    tex = tmp_path / "bake.png"
    Image.new("RGB", (4, 4), (180, 120, 60)).save(tex)
    model = SourceModel(
        source_path=tmp_path / "m.obj",
        geometry=box,
        face_count=len(box.faces),
        object_count=1,
        textures=(tex,),
        colour_signal=ColourSignal.TEXTURE,
    )
    partition = Partition.fresh(len(box.faces))
    frame = partition.create_part("frame")
    partition.assign(np.arange(0, 6), frame)
    cushion = partition.create_part("cushion")
    partition.assign(np.arange(6, 12), cushion)
    dae = tmp_path / "carved.dae"
    export_collada(model, dae, partition=partition)

    reloaded = load_source_model(dae)

    user_parts = [p for p in reloaded.initial_partition.parts if p.id != 0]
    assert len(user_parts) == 2
    assert reloaded.colour_signal is ColourSignal.TEXTURE
    assert reloaded.texture_count == 1               # one shared image, deduped
    assert {p.texture for p in user_parts} == {0}    # both Parts reference it


def test_initial_partition_labels_align_with_the_fused_mesh(tmp_path):
    """The partition's labels line up face-for-face with the fused mesh the pipeline
    uses (export's concatenation), not trimesh's dict order — so each Part owns
    exactly its material's faces in space, never a reshuffled cross-piece mix."""

    def piece(shift, n, colour):
        verts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], float) + [shift, 0, 0]
        faces = np.array([[0, 1, 2], [0, 1, 3], [0, 2, 3]])[:n]
        mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
        mesh.visual = trimesh.visual.TextureVisuals(
            uv=np.zeros((4, 2)), image=Image.new("RGB", (2, 2), colour)
        )
        return mesh

    scene = trimesh.Scene()
    scene.add_geometry(piece(0.0, 1, (255, 0, 0)), geom_name="near0")
    scene.add_geometry(piece(100.0, 2, (0, 0, 255)), geom_name="near100")
    glb = tmp_path / "two.glb"
    scene.export(glb)

    model = load_source_model(glb)
    fused = model.geometry.dump(concatenate=True)  # the same fusion export uses
    labels = model.initial_partition.labels
    centroid_x = fused.triangles.mean(axis=1)[:, 0]

    for part in model.initial_partition.parts:
        if part.id == 0:
            continue
        xs = centroid_x[labels == part.id]
        assert xs.max() - xs.min() < 1.0  # one tight spatial cluster, no mixing


def test_geometry_only_off_loads_with_no_colour_signal(tmp_path):
    """An OFF carries geometry only — like STL it loads as one Unassigned blob with
    colour-signal 'none'."""
    off = tmp_path / "block.off"
    trimesh.creation.box().export(off)

    model = load_source_model(off)

    assert model.colour_signal is ColourSignal.NONE
    assert [p.name for p in model.initial_partition.parts] == ["Unassigned"]


def test_gltf_loads_with_its_material(tmp_path):
    """A .gltf (the text-plus-buffers sibling of .glb) loads through the same path,
    keeping its baked texture."""
    gltf = tmp_path / "one.gltf"
    box = trimesh.creation.box()
    box.visual = trimesh.visual.TextureVisuals(
        uv=np.zeros((len(box.vertices), 2)), image=Image.new("RGB", (4, 4), (90, 160, 90))
    )
    trimesh.Scene({"piece": box}).export(gltf)

    model = load_source_model(gltf)

    assert model.colour_signal is ColourSignal.TEXTURE
    assert model.texture_count == 1
    assert model.face_count == 12
