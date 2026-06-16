"""The viewport's render-mode toggle: Shaded / Wireframe / Edges (#9).

The mode is a bridge view-model property so QML can switch rendering off it and
the transitions are testable headlessly — no 3D scene. The shaded/wireframe/edges
pixels themselves are HITL (#15); here we pin only the state machine.
"""

from __future__ import annotations

from polycut.bridge.processor import Processor


def test_render_mode_defaults_to_shaded():
    """A fresh viewport opens shaded — the model as it will look textured."""
    assert Processor().renderMode == "shaded"


def test_setting_a_valid_mode_transitions_and_notifies():
    """The designer cycles Shaded → Wireframe → Edges; each switch lands on the
    property and emits so QML re-renders."""
    proc = Processor()
    emits = []
    proc.renderModeChanged.connect(lambda: emits.append(proc.renderMode))

    proc.renderMode = "wireframe"
    proc.renderMode = "edges"

    assert proc.renderMode == "edges"
    assert emits == ["wireframe", "edges"]


def test_setting_the_current_mode_again_is_a_no_op():
    """Re-selecting the active mode doesn't churn the signal (no needless re-render)."""
    proc = Processor()
    proc.renderMode = "wireframe"
    emits = []
    proc.renderModeChanged.connect(lambda: emits.append(proc.renderMode))

    proc.renderMode = "wireframe"

    assert proc.renderMode == "wireframe"
    assert emits == []


def test_an_unknown_mode_is_rejected():
    """Only the three real modes are accepted; a stray value leaves the viewport
    on its current mode rather than rendering nothing."""
    proc = Processor()
    emits = []
    proc.renderModeChanged.connect(lambda: emits.append(proc.renderMode))

    proc.renderMode = "hologram"

    assert proc.renderMode == "shaded"
    assert emits == []
