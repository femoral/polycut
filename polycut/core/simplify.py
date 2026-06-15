"""Simplify — texture-preserving decimation of a Source model.

Per ADR-0002 this uses PyMeshLab's quadric edge-collapse-*with-texture* filter:
a Meshy Source model is a single baked-texture blob, and MIT-only simplifiers
(Open3D, fast-simplification) smear that texture under heavy reduction. The
texture-aware quadric collapse respects per-wedge UVs, so the silhouette and the
baked texture both survive.

The mesh is loaded into PyMeshLab straight from the ``.obj`` on disk — that path
reads the native per-wedge texcoords the texture filter needs. After decimation
the wedge UVs are transferred to per-vertex (splitting vertices at UV seams so no
coordinate is averaged across a seam), which is exactly the per-vertex form the
Collada export already consumes.
"""

from __future__ import annotations

import trimesh

from polycut.core.model import SourceModel


def simplify_model(model: SourceModel, target_faces: int) -> SourceModel:
    """Decimate ``model`` toward ``target_faces`` while preserving its texture.

    Returns a new :class:`SourceModel` whose geometry carries the reduced mesh
    with intact UVs; ``texture_path`` is carried over unchanged so the export
    copies the same baked texture beside the output.
    """
    import pymeshlab  # heavy native dep; import lazily so load/export stay light

    ms = pymeshlab.MeshSet()
    ms.load_new_mesh(str(model.source_path))
    ms.meshing_decimation_quadric_edge_collapse_with_texture(
        targetfacenum=int(target_faces),
        preserveboundary=True,  # keep silhouette edges so the outline still reads
        preservenormal=True,
        optimalplacement=True,
    )
    ms.compute_texcoord_transfer_wedge_to_vertex()

    mesh = ms.current_mesh()
    # Carry PyMeshLab's per-vertex normals through so the Collada export reads
    # them directly — trimesh would otherwise recompute them (slow, and pulls in
    # scipy, which isn't a project dependency).
    geometry = trimesh.Trimesh(
        vertices=mesh.vertex_matrix(),
        faces=mesh.face_matrix(),
        vertex_normals=mesh.vertex_normal_matrix(),
        visual=trimesh.visual.TextureVisuals(uv=mesh.vertex_tex_coord_matrix()),
        process=False,
    )

    return SourceModel(
        source_path=model.source_path,
        geometry=geometry,
        face_count=int(mesh.face_number()),
        object_count=1,
        texture_path=model.texture_path,
    )
