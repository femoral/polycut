"""The Preserve view-model: the four simplify toggles (#13).

UV seams / Normals / Boundary edges / Hard edges live as bool properties on the
bridge so QML binds pill toggles to them; flipping one re-runs the cut so the
before/after preview reflects it. These pin the state machine + the re-cut wiring
headlessly with a fake simplifier — the rendered preview itself is HITL.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import trimesh

from polycut.bridge import processor as processor_module
from polycut.bridge.processor import Processor
from polycut.core.model import SceneObject, SourceModel


def _model(path="couch.obj"):
    mesh = trimesh.Trimesh(
        vertices=np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=float),
        faces=np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64),
        vertex_normals=np.tile([0.0, 0.0, 1.0], (4, 1)),
        process=False,
    )
    return SourceModel(
        source_path=Path(path),
        geometry=mesh,
        face_count=200,
        object_count=1,
        texture_path=None,
        objects=(SceneObject(name=Path(path).stem, face_count=200),),
    )


class _RecordingSimplifier:
    """Returns the model unchanged, recording the preserve flags of each cut."""

    def __init__(self, model):
        self.model = model
        self.calls = []  # the PreserveOptions handed to each simplify()

    def simplify(self, target_faces, preserve=None):
        self.calls.append(preserve)
        return self.model

    def close(self):
        pass


def _install(monkeypatch, model):
    fakes = []
    monkeypatch.setattr(processor_module, "load_source_model", lambda p: model)

    def make(m):
        fake = _RecordingSimplifier(m)
        fakes.append(fake)
        return fake

    monkeypatch.setattr(processor_module, "ModelSimplifier", make)
    return fakes


def _load(proc, timeout=5.0):
    deadline = time.time() + timeout
    proc.loadFile("couch.obj")
    while (proc._simplified is None or proc.busy) and time.time() < deadline:
        time.sleep(0.005)


def _settle(proc, timeout=5.0):
    deadline = time.time() + timeout
    while proc.busy and time.time() < deadline:
        time.sleep(0.005)


def test_preserve_defaults():
    """A fresh model: UV seams / Normals / Boundary on, Hard edges off (the AC
    default; reproduces the collapse's prior hardcoded behaviour)."""
    proc = Processor()
    assert proc.preserveUvSeams is True
    assert proc.preserveNormals is True
    assert proc.preserveBoundary is True
    assert proc.preserveHardEdges is False


def test_toggling_a_flag_transitions_and_notifies():
    """Flipping a toggle lands on its property and emits preserveChanged so QML
    re-reads every preserve pill off the one signal."""
    proc = Processor()
    emits = []
    proc.preserveChanged.connect(lambda: emits.append(proc.preserveHardEdges))

    proc.preserveHardEdges = True

    assert proc.preserveHardEdges is True
    assert emits == [True]


def test_setting_the_same_value_is_a_no_op():
    """Re-setting a flag to its current value doesn't churn the signal (or trigger
    a needless re-cut)."""
    proc = Processor()
    emits = []
    proc.preserveChanged.connect(lambda: emits.append(1))

    proc.preserveUvSeams = True  # already on

    assert proc.preserveUvSeams is True
    assert emits == []


def test_toggling_a_flag_re_runs_the_cut_with_the_updated_flags(monkeypatch):
    """Flipping a toggle re-runs the cut, and the worker hands the simplifier the
    updated flags — so the before/after preview reflects the new preserve choice
    (AC#3, verified at the view-model seam)."""
    model = _model()
    fakes = _install(monkeypatch, model)
    proc = Processor()
    _load(proc)  # default cut already ran with boundary on

    proc.preserveBoundary = False
    _settle(proc)

    last = fakes[-1].calls[-1]
    assert last.boundary is False  # the re-cut used the toggled-off flag
    assert proc.preserveBoundary is False


def test_toggling_before_a_model_loads_does_not_cut(monkeypatch):
    """Toggling with no model only updates state — no cut is attempted, so the
    empty state never errors."""
    model = _model()
    fakes = _install(monkeypatch, model)
    proc = Processor()

    proc.preserveNormals = False  # before any load

    assert proc.preserveNormals is False
    assert fakes == []  # no simplifier was ever built — no cut ran
