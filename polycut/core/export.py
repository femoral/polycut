"""Exporting the partition to Collada (.dae) — the "Export to SketchUp" step.

Per ADR-0001 the primary export is ``.dae`` (not native ``.skp``): SketchUp Pro
imports Collada with full material/UV fidelity and it needs no C++ SDK.

The model is carved into **Parts** (slice A/B); this writer emits **shape B**
(ADR-0004): one ``<node>``/``<geometry>`` per Part, Part-named, each with its own
``<material>``/``<effect>`` so SketchUp shows N named, separately-selectable groups
with N swappable material slots. All Parts **share the single baked texture** — one
``<library_images>`` entry, distinct effects sampling it — so the model looks
identical on import but carries reassignable slots. With no partition (or a single
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

from polycut.core.parts import Partition

SHARED_IMAGE_ID = "texture-image"  # one <library_images> entry, shared by all Parts


@dataclass(frozen=True)
class ExportResult:
    """The post-export summary the UI confirms back to the user."""

    output_path: Path
    output_size_bytes: int
    face_count: int
    texture_count: int


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

    texture_name = _copy_texture(model, output_path.parent)
    _write_collada(mesh, partition, output_path, texture_name, unit_name, unit_meters)

    return ExportResult(
        output_path=output_path,
        output_size_bytes=output_path.stat().st_size,
        face_count=int(mesh.faces.shape[0]),
        texture_count=1 if texture_name else 0,
    )


def _copy_texture(model, dest_dir: Path) -> str | None:
    """Copy the baked texture beside the output; return its relative name."""
    if not model.has_texture:
        return None
    dest = dest_dir / model.texture_path.name
    if model.texture_path.resolve() != dest.resolve():
        shutil.copy2(model.texture_path, dest)
    return dest.name


def _single_mesh(geom) -> trimesh.Trimesh:
    """Collapse a Scene to one mesh; pass a Trimesh through untouched."""
    if isinstance(geom, trimesh.Scene):
        return geom.dump(concatenate=True)
    return geom


def _write_collada(
    mesh: trimesh.Trimesh,
    partition: Partition,
    output_path: Path,
    texture_name: str | None,
    unit_name: str,
    unit_meters: float,
) -> None:
    """Build the Collada document — one group per non-empty Part, sharing the texture."""
    doc = Collada()
    doc.assetInfo.unitname = unit_name
    doc.assetInfo.unitmeter = unit_meters

    image = None
    if texture_name:
        image = material.CImage(SHARED_IMAGE_ID, texture_name)
        doc.images.append(image)

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
        nodes.append(
            _build_part(doc, part, mesh.faces[face_idx], vertices, normals, uv, image)
        )

    myscene = scene.Scene("scene0", nodes)
    doc.scenes.append(myscene)
    doc.scene = myscene
    doc.write(str(output_path))


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
