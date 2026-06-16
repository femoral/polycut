"""The Simplify preset / LOD stepper view-model (#14).

A small ladder of named reduction presets (Full / High / Balanced / Low / Min)
sets the simplify target in one click. The preset → target mapping lives on the
bridge; applying a preset runs the same ``simplify(target)`` path the slider uses,
so the slider, the −NN% badge and the before/after preview all follow for free.
These pin the mapping + the stepper's prev/next/clamp/Custom logic headlessly with
a fake simplifier — the rendered preview itself is HITL.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import trimesh

from polycut.bridge import processor as processor_module
from polycut.bridge.processor import Processor
from polycut.core.model import SceneObject, SourceModel


def _model(path="couch.obj", face_count=20000):
    mesh = trimesh.Trimesh(
        vertices=np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=float),
        faces=np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64),
        vertex_normals=np.tile([0.0, 0.0, 1.0], (4, 1)),
        process=False,
    )
    return SourceModel(
        source_path=Path(path),
        geometry=mesh,
        face_count=face_count,
        object_count=1,
        texture_path=None,
        objects=(SceneObject(name=Path(path).stem, face_count=face_count),),
    )


class _RecordingSimplifier:
    """Returns the model unchanged, recording the target of each cut."""

    def __init__(self, model):
        self.model = model
        self.targets = []  # the target_faces handed to each simplify()

    def simplify(self, target_faces, preserve=None):
        self.targets.append(target_faces)
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


def test_apply_preset_sets_the_mapped_target(monkeypatch):
    """Applying the 'Full' preset (keep all, −0%) lands the target on the original
    face count — the mapping reaches the bridge's requested target."""
    model = _model(face_count=20000)
    _install(monkeypatch, model)
    proc = Processor()
    _load(proc)

    proc.applyPreset(0)  # Full — keep all
    _settle(proc)

    assert proc.targetFaceCount == 20000


def test_stepping_through_presets_produces_the_expected_targets(monkeypatch):
    """Each preset maps to its reduction of the 20 000-face original: Full −0%,
    High −50%, Balanced −75%, Low −90%, Min −95% (AC#2)."""
    model = _model(face_count=20000)
    _install(monkeypatch, model)
    proc = Processor()
    _load(proc)

    targets = []
    for index in range(5):
        proc.applyPreset(index)
        _settle(proc)
        targets.append(proc.targetFaceCount)

    assert targets == [20000, 10000, 5000, 2000, 1000]


def test_applying_a_preset_re_runs_the_cut_with_the_mapped_target(monkeypatch):
    """The preset drives a real re-cut: the simplifier is handed the preset's
    target, so the before/after preview reflects it (AC#3, at the view-model seam)."""
    model = _model(face_count=20000)
    fakes = _install(monkeypatch, model)
    proc = Processor()
    _load(proc)  # default cut already ran (Balanced target)

    proc.applyPreset(3)  # Low — −90%
    _settle(proc)

    assert fakes[-1].targets[-1] == 2000  # the re-cut used the Low target


def test_loaded_model_reports_the_balanced_preset(monkeypatch):
    """The default load applies −75%, which is the Balanced preset — so the stepper
    reflects the loaded state out of the box (currentPresetIndex == 2)."""
    model = _model(face_count=20000)
    _install(monkeypatch, model)
    proc = Processor()
    _load(proc)

    assert proc.currentPresetIndex == 2  # Balanced


def test_off_ladder_target_is_custom(monkeypatch):
    """A target that matches no preset — e.g. a slider landing between steps —
    reports Custom (-1), so the stepper can label it honestly."""
    model = _model(face_count=20000)
    _install(monkeypatch, model)
    proc = Processor()
    _load(proc)

    proc.simplify(7400)  # ≈ −63%, between High (−50%) and Balanced (−75%)
    _settle(proc)

    assert proc.currentPresetIndex == -1


def test_simplify_presets_lists_the_ladder_labels():
    """The stepper reads its center labels off the bridge, in ladder order."""
    proc = Processor()
    assert proc.simplifyPresets == ["Full", "High", "Balanced", "Low", "Min"]


def test_step_next_advances_one_rung_and_clamps_at_min(monkeypatch):
    """stepPreset(+1) moves toward more reduction one preset at a time and stops at
    Min — the ladder doesn't wrap."""
    model = _model(face_count=20000)
    _install(monkeypatch, model)
    proc = Processor()
    _load(proc)  # Balanced (2)

    proc.stepPreset(1)
    _settle(proc)
    assert proc.currentPresetIndex == 3  # Low

    proc.stepPreset(1)
    _settle(proc)
    assert proc.currentPresetIndex == 4  # Min

    proc.stepPreset(1)  # already at the end
    _settle(proc)
    assert proc.currentPresetIndex == 4  # clamped, no wrap


def test_step_prev_steps_back_and_clamps_at_full(monkeypatch):
    """stepPreset(-1) moves toward less reduction one preset at a time and stops at
    Full."""
    model = _model(face_count=20000)
    _install(monkeypatch, model)
    proc = Processor()
    _load(proc)  # Balanced (2)

    proc.stepPreset(-1)
    _settle(proc)
    assert proc.currentPresetIndex == 1  # High

    proc.stepPreset(-1)
    _settle(proc)
    assert proc.currentPresetIndex == 0  # Full

    proc.stepPreset(-1)  # already at the start
    _settle(proc)
    assert proc.currentPresetIndex == 0  # clamped, no wrap


def test_step_from_custom_jumps_to_the_adjacent_preset(monkeypatch):
    """From a Custom target (slider between rungs) stepPreset snaps to the nearest
    preset in the step direction — never skipping the rung it sits beside."""
    model = _model(face_count=20000)
    _install(monkeypatch, model)
    proc = Processor()
    _load(proc)

    proc.simplify(7400)  # ≈ −63%, between High (10000) and Balanced (5000)
    _settle(proc)
    assert proc.currentPresetIndex == -1  # Custom

    proc.stepPreset(1)  # more reduction → the next smaller target
    _settle(proc)
    assert proc.currentPresetIndex == 2  # Balanced (5000), not Low

    proc.simplify(7400)  # back to Custom
    _settle(proc)
    proc.stepPreset(-1)  # less reduction → the next larger target
    _settle(proc)
    assert proc.currentPresetIndex == 1  # High (10000)


def test_presets_before_a_model_loads_do_not_cut(monkeypatch):
    """Applying or stepping a preset with no model is inert — no cut is attempted,
    so the empty state never errors."""
    model = _model()
    fakes = _install(monkeypatch, model)
    proc = Processor()

    proc.applyPreset(2)
    proc.stepPreset(1)

    assert proc.currentPresetIndex == -1
    assert fakes == []  # no simplifier was ever built — no cut ran


def test_out_of_range_preset_index_is_ignored(monkeypatch):
    """An index past the ladder is a no-op — it never leaves the loaded Balanced
    target."""
    model = _model(face_count=20000)
    _install(monkeypatch, model)
    proc = Processor()
    _load(proc)

    proc.applyPreset(99)
    _settle(proc)

    assert proc.currentPresetIndex == 2  # unchanged — still Balanced
