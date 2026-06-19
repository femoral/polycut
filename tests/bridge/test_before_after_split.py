"""The before/after split: the bridge feeds the original and the simplified as
two separate mesh views, and surfaces an in-progress signal (#10).

Per ADR-0003 / #10 the render is decoupled from the cut: on load the original
renders immediately and the simplified side computes async, swapping in when the
cut lands — the viewport never blocks on the CPU cut. These drive the bridge
headless with fake geometry (a real tiny trimesh, no PyMeshLab); the split UI,
the dimming, and the chip are visual and verified by eye (HITL, #15).
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import numpy as np
import trimesh

from polycut.bridge import processor as processor_module
from polycut.bridge.processor import Processor
from polycut.core.model import SourceModel


def _quad_model(path, texture=None):
    """A real 2-triangle quad as a SourceModel — fast, exact, render-ready."""
    vertices = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=np.float64)
    faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    normals = np.tile([0.0, 0.0, 1.0], (4, 1))
    uv = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float64)
    mesh = trimesh.Trimesh(
        vertices=vertices,
        faces=faces,
        vertex_normals=normals,
        visual=trimesh.visual.TextureVisuals(uv=uv),
        process=False,
    )
    return SourceModel(
        source_path=Path(path),
        geometry=mesh,
        face_count=2,
        object_count=1,
        texture_path=Path(texture) if texture else None,
    )


def _triangle_model(path):
    """A coarser 1-triangle mesh — stands in for a more aggressive cut."""
    mesh = trimesh.Trimesh(
        vertices=np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float64),
        faces=np.array([[0, 1, 2]], dtype=np.int64),
        vertex_normals=np.tile([0.0, 0.0, 1.0], (3, 1)),
        process=False,
    )
    return SourceModel(
        source_path=Path(path),
        geometry=mesh,
        face_count=1,
        object_count=1,
        texture_path=None,
    )


class _GatedSimplifier:
    """A simplifier whose cut blocks on a gate, so a test can observe the bridge
    while a cut is still in flight (the async, not-yet-swapped-in window)."""

    def __init__(self, model, result, gate):
        self.model = model
        self._result = result
        self._gate = gate

    def simplify(self, target_faces, preserve=None):
        self._gate.wait(timeout=5.0)
        return self._result

    def close(self):
        pass


def _tris(source):
    """The source's current triangle count, or None before it has been fed."""
    buffers = source.current()
    return buffers.triangle_count if buffers else None


def _verts(source):
    """The source's current vertex count, or None before it has been fed."""
    buffers = source.current()
    return buffers.vertex_count if buffers else None


def _wait(predicate, timeout=5.0):
    deadline = time.time() + timeout
    while not predicate() and time.time() < deadline:
        time.sleep(0.005)
    return predicate()


def test_original_renders_immediately_without_waiting_for_the_cut(monkeypatch):
    """On load the original mesh is exposed at once; the viewport never blocks on
    the CPU cut (ADR-0003). The simplified side is still empty while the cut runs."""
    quad = _quad_model("a.obj", texture="baked.png")
    gate = threading.Event()
    monkeypatch.setattr(processor_module, "load_source_model", lambda p: quad)
    monkeypatch.setattr(
        processor_module,
        "ModelSimplifier",
        lambda m: _GatedSimplifier(m, quad, gate),
    )

    proc = Processor()
    proc.loadFile("a.obj")

    # The original appears before the (still-blocked) cut can finish.
    assert _wait(lambda: proc.originalMesh.ready), "original did not render on load"
    assert _tris(proc.originalMesh) == 2
    assert _verts(proc.originalMesh) == 4
    assert proc.originalMesh.textureUrl.fileName() == "baked.png"
    assert proc.simplifiedMesh.ready is False  # simplified side waits for the cut

    gate.set()  # let the cut finish so the worker thread can wind down


def test_simplifying_is_true_while_a_cut_runs_and_false_once_it_settles(monkeypatch):
    """The in-progress signal tracks the async cut — true while computing, false
    when the fresh mesh has swapped in. (Drives the teal 'simplifying…' chip.)"""
    quad = _quad_model("a.obj")
    gate = threading.Event()
    monkeypatch.setattr(processor_module, "load_source_model", lambda p: quad)
    monkeypatch.setattr(
        processor_module,
        "ModelSimplifier",
        lambda m: _GatedSimplifier(m, quad, gate),
    )

    proc = Processor()
    proc.loadFile("a.obj")

    assert _wait(lambda: proc.simplifying is True), "cut never signalled in-progress"

    gate.set()  # the cut lands
    assert _wait(lambda: proc.simplifying is False), "still signalling after settle"
    assert proc.simplifiedMesh.ready is True  # the fresh mesh swapped in


def test_original_stays_fixed_while_the_after_side_recuts(monkeypatch):
    """The before side is the pristine original; re-cutting to a new target only
    swaps the after side. (The split compares against an unchanging original.)"""
    quad = _quad_model("a.obj")
    triangle = _triangle_model("a.obj")
    open_gate = threading.Event()
    open_gate.set()
    monkeypatch.setattr(processor_module, "load_source_model", lambda p: quad)
    monkeypatch.setattr(
        processor_module,
        "ModelSimplifier",
        lambda m: _GatedSimplifier(m, quad, open_gate),
    )

    proc = Processor()
    proc.loadFile("a.obj")  # default reduction → quad
    assert _wait(lambda: _tris(proc.simplifiedMesh) == 2)

    # A more aggressive cut returns the triangle; the original must not move.
    proc._simplifier._result = triangle
    proc.simplify(1)
    assert _wait(lambda: _tris(proc.simplifiedMesh) == 1)

    assert _tris(proc.originalMesh) == 2  # before side unchanged
    assert _verts(proc.originalMesh) == 4


def test_opening_another_model_swaps_the_original(monkeypatch):
    """Loading a different model re-frames the split on the new geometry — the
    before side follows the newly opened original, no stale mesh."""
    models = {"a.obj": _quad_model("a.obj"), "b.obj": _triangle_model("b.obj")}
    monkeypatch.setattr(
        processor_module, "load_source_model", lambda p: models[Path(p).name]
    )
    # A simplifier that just echoes its own model through an already-open gate.
    open_gate = threading.Event()
    open_gate.set()
    monkeypatch.setattr(
        processor_module,
        "ModelSimplifier",
        lambda m: _GatedSimplifier(m, m, open_gate),
    )

    proc = Processor()
    proc.loadFile("a.obj")
    assert _wait(lambda: _tris(proc.originalMesh) == 2)

    proc.loadFile("b.obj")
    assert _wait(lambda: _tris(proc.originalMesh) == 1)
    assert _verts(proc.originalMesh) == 3
