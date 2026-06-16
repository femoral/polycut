"""The bridge must never run two simplifications at once.

PyMeshLab/VCG is not thread-safe; two concurrent decimations corrupt the heap
and abort the process. Rapid slider releases (and the load-time default reduction
overlapping a user drag) must therefore be serialized — one decimation at a time,
coalescing to the latest requested target.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from types import SimpleNamespace

from polycut.bridge import processor as processor_module
from polycut.bridge.processor import Processor


def _wait_idle(proc: Processor, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while proc.busy and time.time() < deadline:
        time.sleep(0.01)


def test_simplify_requests_never_overlap(monkeypatch):
    """Several simplify() calls in flight run serially and settle on the last."""
    live = {"now": 0, "peak": 0}
    guard = threading.Lock()

    class FakeSimplifier:
        """A loaded simplifier whose re-cut holds long enough to expose overlaps."""

        def __init__(self, model):
            self.model = model

        def simplify(self, target_faces):
            with guard:
                live["now"] += 1
                live["peak"] = max(live["peak"], live["now"])
            time.sleep(0.05)  # hold the "decimation" open so overlaps would be visible
            with guard:
                live["now"] -= 1
            return SimpleNamespace(
                face_count=target_faces, has_texture=False, texture_path=None
            )

        def close(self):
            pass

    monkeypatch.setattr(processor_module, "ModelSimplifier", FakeSimplifier)

    proc = Processor()
    proc._model = SimpleNamespace(face_count=1000, source_path=Path("model.obj"))

    for target in (800, 500, 200):
        proc.simplify(target)

    _wait_idle(proc)

    assert live["peak"] == 1  # never two decimations at once
    assert proc.faceCount == 200  # settles on the most recent request
