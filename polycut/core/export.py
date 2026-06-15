"""Exporting a Source model to Collada (.dae) — the "Export to SketchUp" step.

Per ADR-0001 the primary export is ``.dae`` (not native ``.skp``): SketchUp Pro
imports Collada with full material/UV fidelity and it needs no C++ SDK.

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


@dataclass(frozen=True)
class ExportResult:
    """The post-export summary the UI confirms back to the user."""

    output_path: Path
    output_size_bytes: int
    face_count: int
    texture_count: int


def export_collada(model, output_path) -> ExportResult:
    """Write ``model`` to a textured ``.dae`` and report what was produced.

    The geometry passes through unchanged (no simplify/scale in this slice).
    When the model carries a texture it is copied next to the output and
    referenced by relative name, so the ``.dae`` and its image travel together.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    texture_name = _copy_texture(model, output_path.parent)
    mesh = _single_mesh(model.geometry)
    _write_collada(mesh, output_path, texture_name)

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


def _write_collada(mesh: trimesh.Trimesh, output_path: Path, texture_name: str | None) -> None:
    """Build a Collada document for ``mesh`` (textured if ``texture_name``)."""
    doc = Collada()

    effect, materials, images = _build_material(doc, texture_name)
    doc.effects.append(effect)
    for img in images:
        doc.images.append(img)
    doc.materials.append(materials)

    geom = _build_geometry(doc, mesh)
    doc.geometries.append(geom)

    matnode = scene.MaterialNode("materialref", materials, inputs=[("UVSET0", "TEXCOORD", "0")])
    geomnode = scene.GeometryNode(geom, [matnode])
    node = scene.Node("node0", children=[geomnode])
    myscene = scene.Scene("scene0", [node])
    doc.scenes.append(myscene)
    doc.scene = myscene

    doc.write(str(output_path))


def _build_material(doc: Collada, texture_name: str | None):
    """A textured (or plain) effect + material. Returns (effect, material, images)."""
    if texture_name:
        image = material.CImage("texture-image", texture_name)
        surface = material.Surface("texture-surface", image)
        sampler = material.Sampler2D("texture-sampler", surface)
        diffuse = material.Map(sampler, "UVSET0")
        effect = material.Effect("effect0", [surface, sampler], "lambert", diffuse=diffuse)
        mat = material.Material("material0", "material0", effect)
        return effect, mat, [image]

    effect = material.Effect("effect0", [], "lambert", diffuse=(0.6, 0.6, 0.6))
    mat = material.Material("material0", "material0", effect)
    return effect, mat, []


def _build_geometry(doc: Collada, mesh: trimesh.Trimesh) -> geometry.Geometry:
    """A Collada geometry sharing one index per corner for vertex/normal/uv."""
    vert_src = source.FloatSource(
        "verts-array", np.asarray(mesh.vertices, dtype=np.float32).ravel(), ("X", "Y", "Z")
    )
    normal_src = source.FloatSource(
        "normals-array", np.asarray(mesh.vertex_normals, dtype=np.float32).ravel(), ("X", "Y", "Z")
    )
    uv = mesh.visual.uv if mesh.visual.uv is not None else np.zeros((len(mesh.vertices), 2))
    uv_src = source.FloatSource(
        "uv-array", np.asarray(uv, dtype=np.float32).ravel(), ("S", "T")
    )

    geom = geometry.Geometry(doc, "geometry0", "model", [vert_src, normal_src, uv_src])

    input_list = source.InputList()
    input_list.addInput(0, "VERTEX", "#verts-array")
    input_list.addInput(1, "NORMAL", "#normals-array")
    input_list.addInput(2, "TEXCOORD", "#uv-array", set="0")

    # vertex / normal / texcoord all share the per-vertex index, so each face
    # corner repeats its index across the three inputs.
    indices = np.repeat(np.asarray(mesh.faces, dtype=np.int64), 3, axis=1).ravel()
    triset = geom.createTriangleSet(indices, input_list, "materialref")
    geom.primitives.append(triset)
    return geom
