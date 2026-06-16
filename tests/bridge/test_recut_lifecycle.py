"""The bridge re-cuts from memory and disposes the loaded mesh on open-another.

Per #18, the bridge holds one :class:`ModelSimplifier` for the current model so
repeated slider settles re-cut from memory instead of re-parsing the ``.obj``.
Opening another model must dispose the previous one — no leak, no stale geometry.
These drive the bridge with a fake simplifier so they stay fast (no PyMeshLab).
"""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

from polycut.bridge import processor as processor_module
from polycut.bridge.processor import Processor


class FakeSimplifier:
    """Records its lifecycle so tests can assert load-once / dispose behaviour."""

    instances: list["FakeSimplifier"] = []

    def __init__(self, model) -> None:
        self.model = model
        self.cuts: list[int] = []
        self.closed = False
        FakeSimplifier.instances.append(self)

    def simplify(self, target_faces):
        self.cuts.append(target_faces)
        return SimpleNamespace(
            face_count=target_faces, has_texture=False, texture_path=None
        )

    def close(self) -> None:
        self.closed = True


def _fake_model(path):
    return SimpleNamespace(
        face_count=1000,
        source_path=Path(path),
        object_count=1,
        has_texture=False,
        texture_path=None,
    )


def _wait_settled(proc: Processor, timeout: float = 5.0) -> None:
    """Block until a load + its default cut have fully settled."""
    deadline = time.time() + timeout
    while (proc._simplified is None or proc.busy) and time.time() < deadline:
        time.sleep(0.005)


def test_open_another_disposes_previous_simplifier(monkeypatch):
    """Loading a second model closes the first model's simplifier, keeps the new."""
    FakeSimplifier.instances.clear()
    monkeypatch.setattr(processor_module, "ModelSimplifier", FakeSimplifier)
    monkeypatch.setattr(processor_module, "load_source_model", _fake_model)

    proc = Processor()
    proc.loadFile("a.obj")
    _wait_settled(proc)
    proc.loadFile("b.obj")
    _wait_settled(proc)

    assert len(FakeSimplifier.instances) == 2  # one simplifier per model
    first, second = FakeSimplifier.instances
    assert first.closed is True  # previous loaded mesh disposed
    assert second.closed is False  # current one still live
    assert first.model is not second.model  # each bound to its own model


def test_repeated_cuts_reuse_one_simplifier(monkeypatch):
    """Several targets on the same loaded model share a single simplifier."""
    FakeSimplifier.instances.clear()
    monkeypatch.setattr(processor_module, "ModelSimplifier", FakeSimplifier)
    monkeypatch.setattr(processor_module, "load_source_model", _fake_model)

    proc = Processor()
    proc.loadFile("a.obj")
    _wait_settled(proc)

    for target in (800, 500, 200):
        proc.simplify(target)
    deadline = time.time() + 5.0
    while proc.busy and time.time() < deadline:
        time.sleep(0.005)

    assert len(FakeSimplifier.instances) == 1  # parsed once, re-cut from memory
    assert proc.faceCount == 200  # settled on the most recent target
