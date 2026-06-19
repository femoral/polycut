"""The one universal processing indicator (#29, MVP-3 slice J).

Every in-flight operation surfaces in one place: a single ``processingLabel`` on
the Processor, empty when idle and otherwise the op-specific caption the on-canvas
chip shows — ``loading…`` / ``simplifying…`` / ``exporting…`` / ``clustering…``.
The label is set synchronously when an op starts (before its worker spawns) and
clears when the op settles, so the chip is visible in every render mode and framing.

Each worker is gated on a ``threading.Event`` the test can close, so the in-flight
state can be observed deterministically (an instant fake worker would otherwise race
the assertion). Driven directly as a QObject — the chip pixels stay HITL.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from types import SimpleNamespace

from polycut.bridge import processor as processor_module
from polycut.bridge.processor import Processor
from polycut.core.model import SceneObject, SourceModel

from .test_parts_view import _pick_mesh  # the textured pickable mesh + helpers


def _geom_source_model(path, mesh):
    return SourceModel(
        source_path=Path(path), geometry=mesh, face_count=int(mesh.faces.shape[0]),
        object_count=1, texture_path=None,
        objects=(SceneObject(name=Path(path).stem, face_count=int(mesh.faces.shape[0])),),
    )


class _GatedSimplifier:
    """Returns the model unchanged, but blocks in ``simplify`` until the gate opens —
    so a cut can be held in flight while the label is asserted."""

    def __init__(self, model, gate):
        self.model = model
        self.gate = gate

    def simplify(self, target_faces, preserve=None):
        self.gate.wait()
        return self.model

    def close(self):
        pass


def _patched(monkeypatch):
    """A Processor whose load / simplify / export workers each block on a gate the
    test can close. Gates start open, so a plain load + cut settles normally."""
    mesh, _, _ = _pick_mesh()
    model = _geom_source_model("couch.obj", mesh)
    gates = {k: threading.Event() for k in ("load", "simplify", "export")}
    for g in gates.values():
        g.set()  # open by default

    def _load_src(_path):
        gates["load"].wait()
        return model

    def _export(out_model, out_path, *_a, **_kw):
        gates["export"].wait()
        return SimpleNamespace(
            output_path=Path(out_path), output_size_bytes=1,
            face_count=out_model.face_count, texture_count=0,
        )

    monkeypatch.setattr(processor_module, "load_source_model", _load_src)
    monkeypatch.setattr(processor_module, "ModelSimplifier", lambda m: _GatedSimplifier(m, gates["simplify"]))
    monkeypatch.setattr(processor_module, "export_model", _export)
    return Processor(), gates


def _settle(proc, timeout=5.0):
    deadline = time.time() + timeout
    while proc.busy and time.time() < deadline:
        time.sleep(0.005)


def _load(proc, timeout=5.0):
    proc.loadFile("couch.obj")
    deadline = time.time() + timeout
    while (proc._simplified is None or proc.busy) and time.time() < deadline:
        time.sleep(0.005)


def _wait_label(proc, label, timeout=5.0):
    """Wait until the label reaches ``label`` (a worker thread may set it)."""
    deadline = time.time() + timeout
    while proc.processingLabel != label and time.time() < deadline:
        time.sleep(0.005)
    return proc.processingLabel


def test_processing_label_is_empty_when_idle():
    """A fresh Processor with nothing running shows no processing label — the chip
    is hidden until an op is in flight."""
    assert Processor().processingLabel == ""


def test_processing_label_reads_simplifying_during_a_cut(monkeypatch):
    """A simplify in flight reads 'simplifying…'; the label clears when it settles."""
    proc, gates = _patched(monkeypatch)
    _load(proc)  # the default −75% cut settles → idle

    gates["simplify"].clear()  # hold the next cut in flight
    proc.simplify(proc.targetFaceCount)

    assert proc.processingLabel == "simplifying…"  # set synchronously on kickoff
    gates["simplify"].set()
    _settle(proc)
    assert proc.processingLabel == ""  # cleared when the cut lands


def test_processing_label_reads_loading_during_a_load(monkeypatch):
    """A load in flight reads 'loading…'; after the model lands and its default cut
    settles, the label clears."""
    proc, gates = _patched(monkeypatch)

    gates["load"].clear()  # hold the load in flight
    proc.loadFile("couch.obj")

    assert proc.processingLabel == "loading…"  # set synchronously on kickoff
    gates["load"].set()
    deadline = time.time() + 5.0  # already loading — wait for model + default cut
    while (proc._simplified is None or proc.busy) and time.time() < deadline:
        time.sleep(0.005)
    assert proc.processingLabel == ""


def test_processing_label_reads_exporting_during_an_export(monkeypatch):
    """An export in flight reads 'exporting…'; the label clears when it finishes."""
    proc, gates = _patched(monkeypatch)
    _load(proc)

    gates["export"].clear()  # hold the export in flight
    proc.exportModel("out.dae")

    assert proc.processingLabel == "exporting…"  # set synchronously on kickoff
    gates["export"].set()
    _settle(proc)
    assert proc.processingLabel == ""


def test_processing_label_reads_clustering_during_an_off_thread_cluster(qapp, monkeypatch):
    """A cluster runs off-thread in the Parts view-model; the Processor folds its
    clustering flag into the one universal label, so the chip reads 'clustering…'
    while it runs and clears when the relabel lands."""
    proc, _ = _patched(monkeypatch)
    _load(proc)  # parts rebound to the simplified mesh → idle
    parts = proc.parts
    parts.activeTool = "cluster"

    parts.pick(49.5, 49.5, [0.0, 0.0, 5.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0], 60.0, 100, 100)

    assert parts.clustering is True
    assert proc.processingLabel == "clustering…"  # folded in from parts.clustering

    deadline = time.time() + 5.0  # let the worker's relabel land on the GUI thread
    while parts.clustering and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.005)
    qapp.processEvents()
    assert proc.processingLabel == ""
