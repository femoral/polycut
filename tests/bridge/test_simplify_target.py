"""Target-face clamping on the bridge.

The reduction slider derives everything from the bridge's ``targetFaceCount``. A
model smaller than the ``MIN_FACES`` floor used to clamp *up* to the floor —
above the model's own face count — which drove the slider's −NN% badge negative
(a model with 24 faces showed a −317% reduction). These pin the clamp.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import trimesh

from polycut.bridge import processor as processor_module
from polycut.bridge.processor import Processor
from polycut.core.model import SceneObject, SourceModel


def _tiny_model(path, face_count):
    """A SourceModel reporting ``face_count`` (its geometry is a throwaway quad)."""
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
        textures=(),
        objects=(SceneObject(name=Path(path).stem, face_count=face_count),),
    )


class _FakeSimplifier:
    def __init__(self, model):
        self.model = model

    def simplify(self, target_faces, preserve=None):
        return self.model

    def close(self):
        pass


def _load(proc, model, path="tiny.obj", timeout=5.0):
    deadline = time.time() + timeout
    proc.loadFile(path)
    while (proc._simplified is None or proc.busy) and time.time() < deadline:
        time.sleep(0.005)


def test_target_never_exceeds_a_model_below_the_floor(monkeypatch):
    """A model with fewer faces than MIN_FACES clamps to its own size, not up to
    the floor — so the target stays at-or-below the original and the reduction
    badge can't go negative."""
    model = _tiny_model("tiny.obj", face_count=24)  # 24 < MIN_FACES (100)
    monkeypatch.setattr(processor_module, "load_source_model", lambda p: model)
    monkeypatch.setattr(
        processor_module, "ModelSimplifier", lambda m: _FakeSimplifier(m)
    )

    proc = Processor()
    _load(proc, model)

    assert proc.targetFaceCount <= proc.originalFaceCount
    assert proc.reductionPercent >= 0
