"""The Scene Outliner view-model the left panel binds to (#11).

The bridge surfaces the loaded model's composition (one row per object, its face
count) and the selection state, so QML can render the list + highlight the chosen
object — without a 3D scene. The highlight pixels themselves are HITL (#15); here
we pin the observable view-model: contents reflect the file, selection notifies.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import trimesh

from polycut.bridge import processor as processor_module
from polycut.bridge.processor import Processor
from polycut.core.model import SceneObject, SourceModel


def _model_with_objects(path, objects):
    """A SourceModel whose outliner composition is ``objects`` (name, face_count).

    The geometry is a throwaway quad — these tests pin the bridge's *exposure* of
    ``model.objects``, not the mesh — so the listing is independent of the render.
    """
    mesh = trimesh.Trimesh(
        vertices=np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=float),
        faces=np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64),
        vertex_normals=np.tile([0.0, 0.0, 1.0], (4, 1)),
        process=False,
    )
    objs = tuple(SceneObject(name=n, face_count=f) for n, f in objects)
    return SourceModel(
        source_path=Path(path),
        geometry=mesh,
        face_count=sum(f for _, f in objects),
        object_count=len(objects),
        texture_path=None,
        objects=objs,
    )


class _FakeSimplifier:
    """Returns the model unchanged per cut — the outliner ignores the simplified side."""

    def __init__(self, model):
        self.model = model

    def simplify(self, target_faces):
        return self.model

    def close(self):
        pass


def _load(proc, model, path="couch.obj", timeout=5.0):
    """Drive a load through the public slot and wait for it to settle."""
    deadline = time.time() + timeout
    proc.loadFile(path)
    while (not proc.hasModel or proc.busy) and time.time() < deadline:
        time.sleep(0.005)


def test_outliner_lists_the_loaded_models_objects(monkeypatch):
    """After a load, outlinerObjects mirrors the file's composition — name + faces."""
    model = _model_with_objects("couch.obj", [("couch", 2), ("couch.1", 1)])
    monkeypatch.setattr(processor_module, "load_source_model", lambda p: model)
    monkeypatch.setattr(
        processor_module, "ModelSimplifier", lambda m: _FakeSimplifier(m)
    )

    proc = Processor()
    _load(proc, model)

    assert proc.outlinerObjects == [
        {"name": "couch", "faceCount": 2},
        {"name": "couch.1", "faceCount": 1},
    ]


def test_first_object_is_selected_on_load(monkeypatch):
    """Loading auto-selects the first row — the outliner is never left blank, and
    the status bar has a 'Selected:' value at once. Before any load, none is."""
    model = _model_with_objects("couch.obj", [("couch", 2), ("couch.1", 1)])
    monkeypatch.setattr(processor_module, "load_source_model", lambda p: model)
    monkeypatch.setattr(
        processor_module, "ModelSimplifier", lambda m: _FakeSimplifier(m)
    )

    proc = Processor()
    assert proc.selectedObjectIndex == -1  # nothing loaded yet

    _load(proc, model)

    assert proc.selectedObjectIndex == 0


def test_selecting_a_row_updates_and_notifies(monkeypatch):
    """Choosing a different row moves the selection and emits selectionChanged once;
    re-selecting the same row is a no-op (no redundant highlight repaint)."""
    model = _model_with_objects("couch.obj", [("couch", 2), ("couch.1", 1)])
    monkeypatch.setattr(processor_module, "load_source_model", lambda p: model)
    monkeypatch.setattr(
        processor_module, "ModelSimplifier", lambda m: _FakeSimplifier(m)
    )

    proc = Processor()
    _load(proc, model)  # auto-selects row 0
    emits = []
    proc.selectionChanged.connect(lambda: emits.append(proc.selectedObjectIndex))

    proc.selectedObjectIndex = 1
    assert proc.selectedObjectIndex == 1
    assert emits == [1]

    proc.selectedObjectIndex = 1  # same row — no churn
    assert emits == [1]


def test_an_out_of_range_selection_is_rejected(monkeypatch):
    """Only existing rows are selectable — a stray index leaves the selection put."""
    model = _model_with_objects("couch.obj", [("couch", 2), ("couch.1", 1)])
    monkeypatch.setattr(processor_module, "load_source_model", lambda p: model)
    monkeypatch.setattr(
        processor_module, "ModelSimplifier", lambda m: _FakeSimplifier(m)
    )

    proc = Processor()
    _load(proc, model)  # selects row 0

    proc.selectedObjectIndex = 5  # only rows 0 and 1 exist
    assert proc.selectedObjectIndex == 0

    proc.selectedObjectIndex = -3
    assert proc.selectedObjectIndex == 0


def test_selected_object_name_follows_the_selection(monkeypatch):
    """The selected row's name is surfaced for the status bar's 'Selected: <object>'
    narration (design-system §7) — empty when nothing is loaded."""
    model = _model_with_objects("couch.obj", [("couch", 2), ("couch.1", 1)])
    monkeypatch.setattr(processor_module, "load_source_model", lambda p: model)
    monkeypatch.setattr(
        processor_module, "ModelSimplifier", lambda m: _FakeSimplifier(m)
    )

    proc = Processor()
    assert proc.selectedObjectName == ""

    _load(proc, model)
    assert proc.selectedObjectName == "couch"

    proc.selectedObjectIndex = 1
    assert proc.selectedObjectName == "couch.1"
