"""Exporting the partition to Collada (.dae) — the "Export to SketchUp" step.

Per ADR-0001 the primary export is ``.dae`` (not native ``.skp``): SketchUp Pro
imports Collada with full material/UV fidelity and it needs no C++ SDK.

The model is carved into **Parts** (slice A/B); this writer emits **shape B**
(ADR-0004): one ``<node>``/``<geometry>`` per Part, Part-named, each with its own
``<material>``/``<effect>`` so SketchUp shows N named, separately-selectable groups
with N swappable material slots. Each Part's effect samples **its own** texture —
one ``<library_images>`` entry per distinct source image (ADR-0007 multi-texture),
each Part referencing its image by index. A single-texture model emits one shared
image (every Part samples it) — parity with today. With no partition (or a single
Unassigned Part owning everything) this degrades to today's single-group export.

trimesh's own Collada writer drops the baked texture (it emits materials but no
``<library_images>``), so the document is built directly with pycollada: the
texture is copied beside the ``.dae`` and referenced relatively, giving a
self-contained, portable export.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import trimesh
from collada import Collada, geometry, material, scene, source
from PIL import Image

from polycut.core.parts import Partition
from polycut.core.transform import Transform

IMAGE_ID = "texture-image"  # <library_images> id stem; one entry per distinct texture


@dataclass(frozen=True)
class ExportResult:
    """The post-export summary the UI confirms back to the user."""

    output_path: Path
    output_size_bytes: int
    face_count: int
    texture_count: int


def export_model(
    model,
    output_path,
    transform: Transform,
    partition: Partition | None = None,
) -> ExportResult:
    """Run the whole transform→parts→export pipeline and write the ``.dae``.

    Bakes ``transform`` into the geometry (scale + up-axis), degrades a partition
    whose label count no longer matches the transformed mesh to a single group (a
    stale carve from a prior cut), and writes the Collada file declaring the
    Transform's target unit. The single headless entry point a Qt worker — or a
    future CLI — drives; the Collada writer below stays the low-level writer.
    """
    model = transform.apply(model)
    if partition is not None and len(partition.labels) != model.face_count:
        partition = None  # stale carve (face set changed) — fall back to one group
    return export_collada(
        model,
        output_path,
        partition=partition,
        unit_name=transform.unit_name,
        unit_meters=transform.unit_meters,
    )


def export_collada(
    model,
    output_path,
    partition: Partition | None = None,
    unit_name: str = "meter",
    unit_meters: float = 1.0,
) -> ExportResult:
    """Write ``model`` to a textured ``.dae`` and report what was produced.

    When ``partition`` is given, each non-empty Part becomes its own named group +
    material slot; otherwise the whole mesh exports as a single group (today's
    behaviour). ``unit_name``/``unit_meters`` are declared in the Collada ``<unit>``
    metadata so SketchUp imports at the correct real-world size; the geometry itself
    is already baked to scale by the caller. When the model carries a texture it is
    copied next to the output and referenced by relative name, so the ``.dae`` and
    its image travel together.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    mesh = _single_mesh(model.geometry)
    if partition is None:  # no Parts → one group over the whole mesh
        partition = Partition.fresh(int(mesh.faces.shape[0]))

    texture_names = _copy_textures(model, output_path.parent)
    _write_collada(mesh, partition, output_path, texture_names, unit_name, unit_meters)

    return ExportResult(
        output_path=output_path,
        output_size_bytes=output_path.stat().st_size,
        face_count=int(mesh.faces.shape[0]),
        texture_count=len(texture_names),
    )


def _copy_textures(model, dest_dir: Path) -> list[str]:
    """Copy each distinct source texture beside the output; return their relative
    names, parallel to ``model.textures`` (so a Part's texture index still selects
    the right one). Basename collisions across source dirs are disambiguated."""
    names: list[str] = []
    used: set[str] = set()
    for texture in model.textures:
        name = texture.name
        if name in used:  # two source textures share a basename — keep both distinct
            name = f"{texture.stem}-{len(names)}{texture.suffix}"
        dest = dest_dir / name
        if texture.resolve() != dest.resolve():
            shutil.copy2(texture, dest)
        used.add(name)
        names.append(name)
    return names


def _single_mesh(geom) -> trimesh.Trimesh:
    """Collapse a Scene to one mesh; pass a Trimesh through untouched."""
    if isinstance(geom, trimesh.Scene):
        return geom.dump(concatenate=True)
    return geom


def _write_collada(
    mesh: trimesh.Trimesh,
    partition: Partition,
    output_path: Path,
    texture_names: list[str],
    unit_name: str,
    unit_meters: float,
) -> None:
    """Build the Collada document — one group per non-empty Part, each sampling its
    own image, with one ``<library_images>`` entry per distinct source texture."""
    doc = Collada()
    doc.assetInfo.unitname = unit_name
    doc.assetInfo.unitmeter = unit_meters

    images = []
    for i, name in enumerate(texture_names):
        image = material.CImage(f"{IMAGE_ID}-{i}", name)
        doc.images.append(image)
        images.append(image)

    # Read the mesh's own cached normals + UVs once; per-Part geometry slices them,
    # never recomputing (a recompute on the heavy mesh is a slow scipy fallback).
    normals = np.asarray(mesh.vertex_normals, dtype=np.float32)
    uv = getattr(mesh.visual, "uv", None)
    if uv is None:
        uv = np.zeros((len(mesh.vertices), 2))
    uv = np.asarray(uv, dtype=np.float32)
    vertices = np.asarray(mesh.vertices, dtype=np.float32)
    labels = partition.labels

    nodes = []
    for part in partition.parts:
        face_idx = np.where(labels == part.id)[0]
        if face_idx.size == 0:  # Unassigned (or any Part) exports only when non-empty
            continue
        image = _part_image(part, images)
        nodes.append(
            _build_part(doc, part, mesh.faces[face_idx], vertices, normals, uv, image)
        )

    myscene = scene.Scene("scene0", nodes)
    doc.scenes.append(myscene)
    doc.scene = myscene
    doc.write(str(output_path))


def _part_image(part, images):
    """The image a Part samples, or ``None`` (untextured slot)."""
    index = _resolve_texture_index(part, len(images))
    return images[index] if index is not None else None


def _resolve_texture_index(part, n_textures: int) -> int | None:
    """Which texture a Part samples: its own ``texture`` index, or — when it has none
    and the model carries a single image — that shared image (single-texture parity).
    ``None`` when the Part has no resolvable texture (an untextured slot)."""
    index = part.texture
    if index is None:
        index = 0 if n_textures == 1 else None
    if index is None or index >= n_textures:
        return None
    return index


def export_gltf(
    model,
    output_path,
    partition: Partition | None = None,
    unit_name: str = "meter",
    unit_meters: float = 1.0,
) -> ExportResult:
    """Write ``model`` to a glTF/GLB (``.glb`` or ``.gltf`` by extension) and report
    what was produced.

    Each non-empty Part becomes one named submesh in a :class:`trimesh.Scene`, with
    its own material referencing its own **embedded** texture (ADR-0007), so a
    ``.glb`` is a single self-contained file of N named, material-slotted pieces. The
    geometry is already baked to scale by the caller; glTF is metric, so
    ``unit_name``/``unit_meters`` are accepted for a uniform writer signature but not
    re-applied. A single-Part model degrades to one mesh + one material.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    mesh = _single_mesh(model.geometry)
    if partition is None:  # no Parts → one group over the whole mesh
        partition = Partition.fresh(int(mesh.faces.shape[0]))

    images = [Image.open(t) for t in model.textures]
    normals = np.asarray(mesh.vertex_normals, dtype=np.float64)
    uv = getattr(mesh.visual, "uv", None)
    if uv is not None:
        uv = np.asarray(uv, dtype=np.float64)
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    labels = partition.labels

    out_scene = trimesh.Scene()
    used_textures: set[int] = set()
    for part in partition.parts:
        face_idx = np.where(labels == part.id)[0]
        if face_idx.size == 0:  # only non-empty Parts become submeshes
            continue
        index = _resolve_texture_index(part, len(images))
        if index is not None:
            used_textures.add(index)
        submesh = _build_submesh(
            mesh.faces[face_idx], vertices, normals, uv, images[index] if index is not None else None
        )
        out_scene.add_geometry(submesh, geom_name=part.name)

    out_scene.export(output_path)
    return ExportResult(
        output_path=output_path,
        output_size_bytes=output_path.stat().st_size,
        face_count=int(mesh.faces.shape[0]),
        texture_count=len(used_textures),
    )


def _build_submesh(part_faces, vertices, normals, uv, image) -> trimesh.Trimesh:
    """One Part's faces as a standalone mesh — only the vertices its faces touch,
    remapped to a local 0-based index, carrying its own UVs + texture (or untextured)."""
    used, inverse = np.unique(part_faces, return_inverse=True)
    local_faces = inverse.reshape(-1, 3)
    submesh = trimesh.Trimesh(
        vertices=vertices[used],
        faces=local_faces,
        vertex_normals=normals[used],
        process=False,
    )
    if image is not None and uv is not None:
        submesh.visual = trimesh.visual.TextureVisuals(uv=uv[used], image=image)
    return submesh


def _build_part(doc, part, part_faces, vertices, normals, uv, image) -> scene.Node:
    """A named ``<node>`` for one Part: its own geometry + material slot."""
    effect, mat = _build_material(doc, part, image)
    doc.effects.append(effect)
    doc.materials.append(mat)

    geom = _build_geometry(doc, part, part_faces, vertices, normals, uv)
    doc.geometries.append(geom)

    matnode = scene.MaterialNode(f"matref-{part.id}", mat, inputs=[("UVSET0", "TEXCOORD", "0")])
    geomnode = scene.GeometryNode(geom, [matnode])
    return scene.Node(f"node-{part.id}", children=[geomnode], name=part.name)


def _build_material(doc, part, image):
    """A distinct effect + Part-named material; textured effects sample the shared
    image, so every slot carries the same baked look but is independently swappable."""
    effect_id, mat_id = f"effect-{part.id}", f"material-{part.id}"
    if image is not None:
        surface = material.Surface(f"surface-{part.id}", image)
        sampler = material.Sampler2D(f"sampler-{part.id}", surface)
        diffuse = material.Map(sampler, "UVSET0")
        effect = material.Effect(effect_id, [surface, sampler], "lambert", diffuse=diffuse)
    else:
        effect = material.Effect(effect_id, [], "lambert", diffuse=(0.6, 0.6, 0.6))
    return effect, material.Material(mat_id, part.name, effect)


def _build_geometry(doc, part, part_faces, vertices, normals, uv) -> geometry.Geometry:
    """A compact Collada geometry for one Part — only the vertices its faces touch,
    remapped to a local 0-based index, sharing one index per corner across inputs."""
    used, inverse = np.unique(part_faces, return_inverse=True)
    local_faces = inverse.reshape(-1, 3).astype(np.int64)

    pid = part.id
    vert_src = source.FloatSource(f"verts-{pid}", vertices[used].ravel(), ("X", "Y", "Z"))
    normal_src = source.FloatSource(f"normals-{pid}", normals[used].ravel(), ("X", "Y", "Z"))
    uv_src = source.FloatSource(f"uv-{pid}", uv[used].ravel(), ("S", "T"))

    geom = geometry.Geometry(
        doc, f"geometry-{pid}", part.name, [vert_src, normal_src, uv_src]
    )
    input_list = source.InputList()
    input_list.addInput(0, "VERTEX", f"#verts-{pid}")
    input_list.addInput(1, "NORMAL", f"#normals-{pid}")
    input_list.addInput(2, "TEXCOORD", f"#uv-{pid}", set="0")

    indices = np.repeat(local_faces, 3, axis=1).ravel()
    triset = geom.createTriangleSet(indices, input_list, f"matref-{pid}")
    geom.primitives.append(triset)
    return geom
