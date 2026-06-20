"""Carved Parts must reach the exported ``.dae`` (#26 → #27 acceptance).

The export the user gets has to mirror the partition they carved — one named
group + material slot per Part — not a single fused mesh (#19 user story 18:
"the Parts I see in the viewport are exactly what exports"). These drive the
public export slot on a real small textured model and assert the written
Collada reflects the carved Parts, not a single group.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import trimesh
from collada import Collada
from PIL import Image

from polycut.bridge.processor import Processor
from polycut.core.model import SourceModel


def _textured_model(directory: Path, n_faces: int = 4) -> SourceModel:
    """A tiny on-disk textured model (independent triangles + a real PNG) the
    exporter can copy + reference, standing in for the simplified sofa."""
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


def _bind_model(proc: Processor, model: SourceModel) -> None:
    """Bind ``model`` as the current (simplified) mesh + rebind the Parts view-model
    to it — the state a settled cut leaves behind, set up without PyMeshLab."""
    proc._model = model
    proc._simplified = model
    proc._parts.rebind(model.geometry, None)


def _wait_export(proc: Processor, out: Path, timeout: float = 5.0) -> None:
    """Block until the off-thread export worker has written ``out`` and cleared busy."""
    deadline = time.time() + timeout
    while (proc.busy or not out.exists()) and time.time() < deadline:
        time.sleep(0.005)


def test_export_writes_the_carved_parts_as_named_groups(qapp, tmp_path):
    """Two carved Parts export as two Part-named material slots — not one fused group."""
    model = _textured_model(tmp_path, n_faces=4)
    proc = Processor()
    _bind_model(proc, model)
    partition = proc._parts._partition
    frame = partition.create_part(name="frame")
    cushions = partition.create_part(name="cushions")
    partition.assign([0, 1], frame)
    partition.assign([2, 3], cushions)

    out = tmp_path / "out.dae"
    proc.exportModel(str(out))
    _wait_export(proc, out)

    doc = Collada(str(out))
    assert {m.name for m in doc.materials} == {"frame", "cushions"}


def test_export_dispatches_to_glb_through_the_worker(qapp, tmp_path):
    """Exporting to a .glb path drives the off-thread worker to the glTF writer — the
    written file is a glTF binary, dispatched by extension (MVP-4 slice I)."""
    model = _textured_model(tmp_path, n_faces=4)
    proc = Processor()
    _bind_model(proc, model)

    out = tmp_path / "out.glb"
    proc.exportModel(str(out))
    _wait_export(proc, out)

    assert out.read_bytes()[:4] == b"glTF"


def test_processor_exposes_the_available_export_formats(qapp):
    """The processor exposes the export formats for the save-dialog filter — DAE, GLB
    and OBJ — so the designer can pick the format when saving."""
    proc = Processor()

    joined = " ".join(proc.exportNameFilters).lower()

    assert "*.dae" in joined and "*.glb" in joined and "*.obj" in joined


def test_export_with_no_parts_carved_writes_a_single_group(qapp, tmp_path):
    """No Parts carved → the model still exports as one valid group, unchanged from
    the pre-Parts single-mesh writer (the fresh all-Unassigned partition is a no-op)."""
    model = _textured_model(tmp_path, n_faces=4)
    proc = Processor()
    _bind_model(proc, model)  # bound, but nothing carved

    out = tmp_path / "out.dae"
    proc.exportModel(str(out))
    _wait_export(proc, out)

    doc = Collada(str(out))
    assert len(doc.geometries) == 1
    assert sum(len(prim) for geom in doc.geometries for prim in geom.primitives) == 4
