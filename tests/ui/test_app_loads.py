"""Headless smoke test: the QML shell loads with no errors.

Visual fidelity is verified manually (per the PRD), but loading the engine
offscreen cheaply catches QML syntax, type, and binding-wiring errors so the
shell can't silently break as later slices add panels. Skipped when PySide6
isn't available.
"""

import os

import pytest

pytest.importorskip("PySide6")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_main_qml_loads_without_errors():
    from PySide6.QtCore import QtMsgType, qInstallMessageHandler
    from PySide6.QtGui import QGuiApplication

    from polycut.app import create_engine

    messages: list[str] = []

    # The 3D viewport can't initialise a GPU backend under the offscreen platform,
    # so QtQuick3D warns it "is not functional" and won't draw. That's purely an
    # environmental limitation of the headless test host — not a QML defect — so it
    # is ignored here; the shaded render is verified by eye (HITL, #15).
    benign = ("not based on QRhi", "Qt Quick 3D is not functional", "isApiRhiBased")

    def handler(mode, _context, message):
        if mode in (QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
            if any(marker in message for marker in benign):
                return
            messages.append(message)

    qInstallMessageHandler(handler)
    try:
        app = QGuiApplication.instance() or QGuiApplication([])
        engine = create_engine(app)
        app.processEvents()  # let bindings settle so late null-deref errors surface

        assert engine.rootObjects(), "Main.qml failed to produce a root object"
        assert not messages, "QML warnings:\n" + "\n".join(messages)
    finally:
        qInstallMessageHandler(None)
