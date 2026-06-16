"""The Transform view-model: up-axis remap + units auto-detect (#12).

The bridge holds the up-axis choice and the source unit. Picking an up-axis
rotates the rendered geometry (the viewport reflects it) and is baked at export;
loading a model auto-fills the source unit from its size, which a manual pick
overrides. These pin the observable view-model with fake geometry — no 3D scene;
the rotated pixels are HITL (#15).
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import trimesh

from polycut.bridge import processor as processor_module
from polycut.bridge.processor import Processor
from polycut.core.model import SourceModel


def _box_model(path, extents, texture=None):
    """A box SourceModel with distinct per-axis extents — rotation is observable."""
    box = trimesh.creation.box(extents=extents)
    mesh = trimesh.Trimesh(
        vertices=box.vertices,
        faces=box.faces,
        vertex_normals=np.tile([0.0, 1.0, 0.0], (len(box.vertices), 1)),
        process=False,
    )
    return SourceModel(
        source_path=Path(path),
        geometry=mesh,
        face_count=int(mesh.faces.shape[0]),
        object_count=1,
        texture_path=Path(texture) if texture else None,
    )


class _FakeSimplifier:
    """Returns the model unchanged per cut — these tests ignore the simplified side."""

    def __init__(self, model):
        self.model = model

    def simplify(self, target_faces):
        return self.model

    def close(self):
        pass


def _install(monkeypatch, model):
    monkeypatch.setattr(processor_module, "load_source_model", lambda p: model)
    monkeypatch.setattr(
        processor_module, "ModelSimplifier", lambda m: _FakeSimplifier(m)
    )


def _load(proc, path="couch.obj", timeout=5.0):
    """Load and wait for the default cut to fully settle — so no simplify worker is
    still in flight to race a later export's ``busy`` flag."""
    deadline = time.time() + timeout
    proc.loadFile(path)
    while (proc._simplified is None or proc.busy) and time.time() < deadline:
        time.sleep(0.005)


def test_up_axis_defaults_to_y():
    """A fresh transform is Y-up — the no-op identity (Meshy's usual orientation)."""
    assert Processor().upAxis == "y"


def test_setting_a_valid_up_axis_transitions_and_notifies():
    """Choosing X / Z lands on the property and emits so QML + the readout refresh."""
    proc = Processor()
    emits = []
    proc.scaleChanged.connect(lambda: emits.append(proc.upAxis))

    proc.upAxis = "z"

    assert proc.upAxis == "z"
    assert emits == ["z"]


def test_an_unknown_up_axis_is_rejected():
    """Only X / Y / Z are valid — a stray value leaves the orientation put."""
    proc = Processor()
    emits = []
    proc.scaleChanged.connect(lambda: emits.append(proc.upAxis))

    proc.upAxis = "w"

    assert proc.upAxis == "y"
    assert emits == []


def test_changing_up_axis_rotates_the_rendered_geometry(monkeypatch):
    """The viewport reflects the up-axis: the rendered mesh's bounds rotate when the
    axis changes (AC#1) — Z-up swaps the model's Y and Z extents."""
    model = _box_model("couch.obj", extents=(1.0, 2.0, 3.0))  # Y extent 2, Z extent 3
    _install(monkeypatch, model)

    proc = Processor()
    _load(proc)
    assert proc.originalMesh.boundsMax.y() == 1.0  # half of the Y extent (2)

    proc.upAxis = "z"  # +Z → +Y: the Z extent (3) becomes the Y extent

    deadline = time.time() + 5.0
    while abs(proc.originalMesh.boundsMax.y() - 1.5) > 1e-4 and time.time() < deadline:
        time.sleep(0.005)
    assert proc.originalMesh.boundsMax.y() == 1.5  # half of the old Z extent (3)


def test_loading_auto_fills_the_detected_source_unit(monkeypatch):
    """On load the source unit is pre-filled from the model's size (AC#2): a
    millimetre-scaled model lands on 'mm', not the default metres."""
    model = _box_model("couch.obj", extents=(1900.0, 950.0, 100.0))  # mm-scaled
    _install(monkeypatch, model)

    proc = Processor()
    assert proc.sourceUnit == "m"  # the default, before any load

    _load(proc)

    assert proc.sourceUnit == "mm"


def test_manual_source_unit_override_is_respected(monkeypatch):
    """A manual unit pick after load sticks — a later cut doesn't re-run detection
    and stomp it (AC#3)."""
    model = _box_model("couch.obj", extents=(1900.0, 950.0, 100.0))  # auto-detects mm
    _install(monkeypatch, model)

    proc = Processor()
    _load(proc)
    assert proc.sourceUnit == "mm"  # auto-filled

    proc.sourceUnit = "cm"  # the designer overrides
    assert proc.sourceUnit == "cm"

    proc.simplify(1)  # another cut settles
    deadline = time.time() + 5.0
    while proc.busy and time.time() < deadline:
        time.sleep(0.005)

    assert proc.sourceUnit == "cm"  # the override survived the cut


def test_export_bakes_up_axis_and_scale(monkeypatch, tmp_path):
    """The exported geometry carries both the scale and the up-axis remap (AC#4):
    a ×2 scale then Z-up turns extents (1,2,3) into (2,6,4)."""
    model = _box_model("couch.obj", extents=(1.0, 2.0, 3.0))
    _install(monkeypatch, model)

    proc = Processor()
    _load(proc)
    proc.scaleMultiplier = 2.0  # source/target both metres → factor 2
    proc.upAxis = "z"

    out = tmp_path / "couch.dae"
    proc.exportModel(str(out))
    deadline = time.time() + 10.0
    while proc.busy and time.time() < deadline:
        time.sleep(0.005)

    exported = trimesh.load(str(out), force="mesh")
    extents = exported.bounds[1] - exported.bounds[0]
    assert np.allclose(extents, (2.0, 6.0, 4.0))
