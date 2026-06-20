"""Per-submesh simplify — imported material-Parts survive the core reduction step.

MVP-4 slice E (ADR-0007): when a model already carries Parts (a multi-material
import), each Part's faces are decimated independently and the partition is remapped
onto the reduced face set, so the carve survives Simplify. Tractable because the
imported materials are already separate pieces (unlike the Meshy soup). The Meshy
single-material path keeps whole-mesh simplify. Pure headless ``core`` — these tests
build a small two-Part model and reduce it.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh
from PIL import Image

from polycut.core.export import export_gltf
from polycut.core.model import SourceModel
from polycut.core.parts import Partition
from polycut.core.simplify import simplify_parts


def _grid(n: int, origin_x: float):
    """An ``n×n`` textured quad grid translated to ``origin_x`` — 2·n² faces."""
    xs = np.linspace(0.0, 1.0, n + 1)
    verts = np.array([(x + origin_x, 0.0, z) for z in xs for x in xs])
    uv = np.array([(x, z) for z in xs for x in xs])
    faces = []
    for j in range(n):
        for i in range(n):
            a, b = j * (n + 1) + i, j * (n + 1) + i + 1
            c, d = (j + 1) * (n + 1) + i + 1, (j + 1) * (n + 1) + i
            faces += [(a, b, c), (a, c, d)]
    return verts, np.array(faces, np.int64), uv


def _two_part_model(directory: Path, n: int = 8):
    """Two separated textured grids fused into one mesh — frame (material 0) and
    cushion (material 1), each its own Part of 2·n² faces."""
    v0, f0, uv0 = _grid(n, 0.0)
    v1, f1, uv1 = _grid(n, 5.0)
    verts = np.vstack([v0, v1])
    faces = np.vstack([f0, f1 + len(v0)])
    uv = np.vstack([uv0, uv1])
    mesh = trimesh.Trimesh(
        vertices=verts, faces=faces,
        visual=trimesh.visual.TextureVisuals(uv=uv), process=False,
    )
    t0 = directory / "frame.png"
    Image.new("RGB", (4, 4), (200, 40, 40)).save(t0)
    t1 = directory / "cushion.png"
    Image.new("RGB", (4, 4), (40, 40, 200)).save(t1)
    model = SourceModel(
        source_path=directory / "m.glb", geometry=mesh, face_count=len(faces),
        object_count=2, textures=(t0, t1),
    )
    face_materials = np.array([0] * len(f0) + [1] * len(f1))
    partition = Partition.from_materials(face_materials, ["frame", "cushion"], [0, 1])
    return model, partition


def test_per_submesh_simplify_preserves_every_part(tmp_path):
    """Reducing a two-Part model keeps both Parts: the remapped partition covers every
    face of the reduced mesh and each Part still owns a non-empty face set."""
    model, partition = _two_part_model(tmp_path, n=8)  # 128 + 128 = 256 faces
    target = model.face_count // 4  # ~25%

    reduced_model, reduced_partition = simplify_parts(model, partition, target)

    user_parts = [p for p in reduced_partition.parts if p.id != 0]
    assert len(user_parts) == 2
    for part in user_parts:
        assert reduced_partition.face_count(part.id) > 0  # no Part decimated away
    covered = sum(reduced_partition.face_count(p.id) for p in reduced_partition.parts)
    assert covered == reduced_model.face_count
    assert len(reduced_partition.labels) == reduced_model.face_count


def test_each_part_reduced_count_tracks_the_target_ratio(tmp_path):
    """The reduction ratio is applied to each submesh, so every Part's reduced face
    count tracks the requested fraction of its own original count."""
    model, partition = _two_part_model(tmp_path, n=8)
    originals = {p.id: partition.face_count(p.id) for p in partition.parts if p.id != 0}
    target = model.face_count // 2  # ratio ~= 0.5

    _, reduced_partition = simplify_parts(model, partition, target)

    for part_id, original in originals.items():
        reduced = reduced_partition.face_count(part_id)
        assert abs(reduced - 0.5 * original) <= 0.25 * original  # ~half its own faces


def test_reduced_model_exports_with_intact_per_part_textures(tmp_path):
    """The reduced model carries intact per-vertex UVs/normals and the remapped
    partition stays aligned, so the exporters consume it directly — a .glb reloads as
    both Parts, textured, covering every reduced face."""
    model, partition = _two_part_model(tmp_path, n=8)
    target = model.face_count // 4

    reduced_model, reduced_partition = simplify_parts(model, partition, target)
    out = tmp_path / "out.glb"
    export_gltf(reduced_model, out, partition=reduced_partition)

    reloaded = trimesh.load(out, process=False)
    assert isinstance(reloaded, trimesh.Scene)
    assert len(reloaded.geometry) == 2
    total = sum(len(g.faces) for g in reloaded.geometry.values())
    assert total == reduced_model.face_count
