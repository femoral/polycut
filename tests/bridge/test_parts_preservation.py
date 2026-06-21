"""Imported and carved Parts must survive simplify + reopen (round-trip bug).

A multi-material model opens already separated into Parts (its ``initial_partition``),
but the bridge dropped them: the load never seeded the Parts panel, and every
simplify rebound the panel to a single fresh Unassigned — so a 2-part ``.dae``
reopened with no Parts, and nudging the slider after carving wiped the carve.

These drive the public bridge surface (load → settle, carve → re-simplify) and
assert the Parts the user sees survive, mirroring what exports.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import trimesh

from polycut.bridge import processor as processor_module
from polycut.bridge.parts_view import PartsViewModel
from polycut.bridge.processor import Processor
from polycut.core.model import SceneObject, SourceModel
from polycut.core.parts import UNASSIGNED_ID, Partition


def _independent_faces(n: int) -> trimesh.Trimesh:
    """A throwaway mesh of ``n`` independent triangles with UVs — enough to bind."""
    verts, faces, uv = [], [], []
    for i in range(n):
        b = i * 3
        verts += [[i, 0, 0], [i + 1, 0, 0], [i, 1, 0]]
        faces.append([b, b + 1, b + 2])
        uv += [[0, 0], [1, 0], [0, 1]]
    mesh = trimesh.Trimesh(vertices=np.array(verts, float), faces=np.array(faces), process=False)
    mesh.visual = trimesh.visual.TextureVisuals(uv=np.array(uv, float))
    return mesh


def _user_parts(view_or_partition) -> list:
    rows = (
        view_or_partition.partsRows
        if isinstance(view_or_partition, PartsViewModel)
        else None
    )
    return [r for r in rows if r["id"] != UNASSIGNED_ID]


def test_rebind_adopts_a_supplied_partition(qapp):
    """rebind can adopt an existing partition — the imported / carried-forward Parts —
    instead of always starting fresh, so a multi-part import's Parts reach the panel."""
    view = PartsViewModel()
    mesh = _independent_faces(4)
    partition = Partition.fresh(4)
    frame = partition.create_part("frame")
    partition.assign([0, 1], frame)

    view.rebind(mesh, None, partition)

    assert view.export_partition() is partition
    assert view.hasParts
    assert {r["name"] for r in _user_parts(view)} == {"frame"}


def _multipart_model(path: str, n_parts: int = 2, faces_each: int = 2) -> SourceModel:
    """A SourceModel that arrives already separated into ``n_parts`` Parts — a
    multi-material import, with an ``initial_partition`` seeding one Part per
    material over a fused throwaway mesh."""
    total = n_parts * faces_each
    mesh = _independent_faces(total)
    partition = Partition.fresh(total)
    for i in range(n_parts):
        pid = partition.create_part(f"part-{i + 1}")
        partition.assign(list(range(i * faces_each, (i + 1) * faces_each)), pid)
    return SourceModel(
        source_path=Path(path),
        geometry=mesh,
        face_count=total,
        object_count=n_parts,
        textures=(),
        objects=(SceneObject(name=Path(path).stem, face_count=total),),
        initial_partition=partition,
    )


def _load_and_settle(proc: Processor, path: str = "import.dae", timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    proc.loadFile(path)
    while (proc._simplified is None or proc.busy) and time.time() < deadline:
        time.sleep(0.005)


def test_importing_a_multipart_model_keeps_its_parts_after_the_default_simplify(qapp, monkeypatch):
    """Opening a multi-material model and letting the default −75% cut settle leaves
    its imported Parts on the panel — not a single Unassigned (the reopen bug)."""
    model = _multipart_model("import.dae", n_parts=2)
    monkeypatch.setattr(processor_module, "load_source_model", lambda p: model)
    # The per-Part simplify is exercised in core's own tests; here it is the identity
    # so the orchestration (which path runs, what gets bound) is what's under test.
    monkeypatch.setattr(
        processor_module, "simplify_parts",
        lambda m, partition, target, preserve: (m, partition),
    )

    proc = Processor()
    _load_and_settle(proc)

    assert proc.parts.hasParts
    assert {r["name"] for r in _user_parts(proc.parts)} == {"part-1", "part-2"}


class _FakeSimplifier:
    """The whole-mesh path's simplifier, returning the model unchanged (the real
    PyMeshLab collapse is exercised in core's tests; here the orchestration is)."""

    def __init__(self, model):
        self.model = model

    def simplify(self, target_faces, preserve=None):
        return self.model

    def close(self):
        pass


def _blob_model(path: str, faces: int = 6) -> SourceModel:
    """A single-material model — opens as one Unassigned blob (the Meshy case)."""
    mesh = _independent_faces(faces)
    return SourceModel(
        source_path=Path(path),
        geometry=mesh,
        face_count=faces,
        object_count=1,
        textures=(),
        objects=(SceneObject(name=Path(path).stem, face_count=faces),),
    )


def _simplify_and_settle(proc: Processor, target: int, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    proc.simplify(target)
    while proc.busy and time.time() < deadline:
        time.sleep(0.005)


def test_resimplifying_a_carved_model_preserves_its_parts(qapp, monkeypatch):
    """Carve Parts on a settled cut, then nudge the slider: the Parts survive the
    re-simplify on the new mesh — they are no longer wiped back to one Unassigned."""
    model = _blob_model("sofa.obj", faces=6)
    monkeypatch.setattr(processor_module, "load_source_model", lambda p: model)
    monkeypatch.setattr(processor_module, "ModelSimplifier", lambda m: _FakeSimplifier(m))
    monkeypatch.setattr(
        processor_module, "simplify_parts",
        lambda m, partition, target, preserve: (m, partition),
    )

    proc = Processor()
    _load_and_settle(proc)
    assert not proc.parts.hasParts  # the blob opens with no user Parts

    partition = proc._parts._partition  # carve two Parts on the settled mesh
    frame = partition.create_part("frame")
    legs = partition.create_part("legs")
    partition.assign([0, 1, 2], frame)
    partition.assign([3, 4], legs)

    _simplify_and_settle(proc, target=4)

    assert {r["name"] for r in _user_parts(proc.parts)} == {"frame", "legs"}


def test_reopening_a_two_part_dae_shows_two_parts_end_to_end(qapp, tmp_path):
    """The reported round-trip, unstubbed: a 2-Part ``.dae`` written by the exporter,
    reopened through the real load → default-simplify path, comes back with its two
    Parts — not a single Unassigned. Real trimesh load + real per-Part PyMeshLab cut."""
    from PIL import Image

    from polycut.core.export import export_collada

    texture = tmp_path / "bake.png"
    Image.new("RGB", (4, 4), (180, 120, 60)).save(texture)
    mesh = _independent_faces(6)
    mesh.visual = trimesh.visual.TextureVisuals(
        uv=np.asarray(mesh.visual.uv, float), image=Image.open(texture)
    )
    model = SourceModel(
        source_path=tmp_path / "src.obj", geometry=mesh,
        face_count=6, object_count=1, textures=(texture,),
    )
    partition = Partition.fresh(6)
    frame = partition.create_part("frame")
    cushions = partition.create_part("cushions")
    partition.assign([0, 1, 2], frame)
    partition.assign([3, 4, 5], cushions)

    dae = tmp_path / "testfile.dae"
    export_collada(model, dae, partition)

    proc = Processor()
    _load_and_settle(proc, path=str(dae))

    assert proc.parts.hasParts
    assert len(_user_parts(proc.parts)) == 2
