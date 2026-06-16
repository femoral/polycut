"""The QML shell mounts the 3D viewport in the center stage (#8).

This is the closest the render path gets to an automated check: loading the real
``Main.qml`` through the app engine (offscreen) proves the QtQuick3D import
resolves, the Python ``MeshGeometry`` type is registered, the ``Theme`` tokens
bind, and the viewport object is actually mounted. The shaded pixels and the
orbit/pan/zoom feel remain HITL (#15) — no offscreen check can stand in for eyes.
"""

from __future__ import annotations

from PySide6.QtCore import QObject

from polycut.app import create_engine


def test_center_stage_mounts_the_viewport(qapp):
    """Main.qml loads cleanly and the viewport is present in the scene."""
    engine = create_engine(qapp)

    roots = engine.rootObjects()
    assert roots, "Main.qml failed to load — QtQuick3D import or a QML error"

    viewport = roots[0].findChild(QObject, "viewport")
    assert viewport is not None, "the center stage did not mount the viewport"
