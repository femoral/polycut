"""Up-axis remap — orienting a Source model upright for SketchUp (#12).

Meshy exports don't share SketchUp's orientation, so the designer states which
source axis points up and the model is rotated so that axis becomes world up.
World up is the viewport's Y (Qt3D convention); the rotation is baked into the
geometry, so the viewport reflects the choice and the export agrees with it.
"""

from __future__ import annotations

import numpy as np
import trimesh

from polycut.core.model import SourceModel


# Rotation that carries each source up-axis onto world up (+Y). "y" is absent —
# it is the identity, handled as a no-op.
_TO_Y = {
    "x": (np.pi / 2, (0, 0, 1)),  # +X → +Y, rotate about Z
    "z": (-np.pi / 2, (1, 0, 0)),  # +Z → +Y, rotate about X
}

UP_AXES = ("x", "y", "z")


def remap_up_axis(model: SourceModel, up_axis: str) -> SourceModel:
    """Return a new :class:`SourceModel` rotated so ``up_axis`` points up (Y).

    ``"y"`` is the no-op identity — the model is already Y-up. The geometry's
    cached vertex normals are rotated by the same matrix (rather than dropped and
    recomputed) so a heavy export needn't fall back to the slow normal recompute.
    """
    if up_axis not in _TO_Y:
        return model

    angle, direction = _TO_Y[up_axis]
    matrix = trimesh.transformations.rotation_matrix(angle, direction)

    # Read the cached normals from the ORIGINAL loaded mesh (it carries them from
    # the OBJ). Reading them from a fresh .copy() instead drops the cache and forces
    # a full normal recompute — a multi-second scipy-fallback grind on the 646k
    # mesh, on every up-axis toggle. Rotate the cached normals onto the copy by hand
    # so the copy never has to recompute its own.
    source = model.geometry
    normals = getattr(source, "vertex_normals", None) if isinstance(
        source, trimesh.Trimesh
    ) else None
    geometry = source.copy()
    geometry.apply_transform(matrix)
    if normals is not None:
        geometry.vertex_normals = normals @ matrix[:3, :3].T

    return SourceModel(
        source_path=model.source_path,
        geometry=geometry,
        face_count=model.face_count,
        object_count=model.object_count,
        textures=model.textures,
        colour_signal=model.colour_signal,
        objects=model.objects,
    )
