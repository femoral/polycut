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

    Stateless: parses the ``.obj`` from disk every call. For repeated cuts of the
    same model (the slider settling on target after target) use
    :class:`ModelSimplifier`, which parses once and re-cuts from memory.
    """
    import pymeshlab  # heavy native dep; import lazily so load/export stay light

    ms = pymeshlab.MeshSet()
    ms.load_new_mesh(str(model.source_path))
    return _collapse_current(ms, target_faces, model)


class ModelSimplifier:
    """Parse a Source model's ``.obj`` once, then re-cut it from memory (#18).

    The 70 MB Meshy ``.obj`` is loaded into a single PyMeshLab ``MeshSet`` at
    construction and kept as the pristine original. Each :meth:`simplify` runs
    the same texture-preserving quadric collapse as :func:`simplify_model`, but
    on a fresh **copy** of that original — never the already-decimated result of
    a prior cut — so repeated slider settles skip the redundant disk re-parse
    while every cut starts from the full-resolution mesh. Output is identical to
    the stateless path (per ADR-0003). Not thread-safe: PyMeshLab/VCG is not, so
    callers must serialize :meth:`simplify` calls.
    """

    def __init__(self, model: SourceModel) -> None:
        import pymeshlab

        self._model = model
        self._ms = pymeshlab.MeshSet()
        self._ms.load_new_mesh(str(model.source_path))  # the one and only parse
        self._original_id = self._ms.current_mesh_id()

    def simplify(self, target_faces: int) -> SourceModel:
        """Re-cut the in-memory original toward ``target_faces``.

        Decimation is destructive, so each call works on a throwaway copy of the
        pristine original and discards it afterwards — keeping memory bounded to
        the original plus one transient cut.
        """
        if self._ms is None:
            raise RuntimeError("ModelSimplifier is closed")

        self._ms.set_current_mesh(self._original_id)
        self._ms.generate_copy_of_current_mesh()  # copy becomes the current mesh
        working_id = self._ms.current_mesh_id()
        try:
            return _collapse_current(self._ms, target_faces, self._model)
        finally:
            self._ms.set_current_mesh(working_id)
            self._ms.delete_current_mesh()  # drop the copy; original stays pristine

    def close(self) -> None:
        """Release the loaded mesh. Idempotent; the instance is unusable after."""
        self._ms = None  # native VCG memory is freed when the MeshSet is collected

    def __enter__(self) -> "ModelSimplifier":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _collapse_current(ms, target_faces: int, model: SourceModel) -> SourceModel:
    """Run the texture-preserving collapse on ``ms``'s current mesh and extract it."""
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
