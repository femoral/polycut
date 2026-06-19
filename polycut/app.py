"""Polycut application entry point — wires the QML shell to the bridge."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from polycut.bridge import Processor
from polycut.bridge import explode_geometry  # noqa: F401 — registers the QML ExplodeChunkGeometry type
from polycut.bridge import buffer_geometry  # noqa: F401 — registers the QML BufferGeometry type
from polycut.resources import base_dir, ui_dir

UI_DIR = ui_dir()
MAIN_QML = UI_DIR / "Polycut" / "Main.qml"
# Dev convenience: the committed Meshy fixture powers the "Load sample" button.
# Not bundled in a packaged build, where the button simply hides.
SAMPLE_MODEL = base_dir() / "tests" / "fixtures" / "meshy_sofa" / "model.obj"


def create_engine(app: QGuiApplication) -> QQmlApplicationEngine:
    engine = QQmlApplicationEngine()
    processor = Processor(engine)
    # Keep a strong Python reference for the engine's lifetime; without it the
    # QObject is garbage-collected after this function returns and QML's
    # `processor` goes null mid-session.
    engine._processor = processor

    context = engine.rootContext()
    context.setContextProperty("processor", processor)
    context.setContextProperty("sampleModelPath", str(SAMPLE_MODEL) if SAMPLE_MODEL.exists() else "")

    engine.addImportPath(str(UI_DIR))
    engine.load(QUrl.fromLocalFile(str(MAIN_QML)))
    return engine


def main() -> int:
    app = QGuiApplication(sys.argv)
    app.setApplicationName("Polycut")
    app.setOrganizationName("Polycut")

    engine = create_engine(app)
    if not engine.rootObjects():
        return 1
    rc = app.exec()

    # Hard-exit instead of unwinding. At normal interpreter shutdown the main thread
    # runs Qt's global/static destructors (libQt6ShaderTools) while glibc is freeing
    # a background worker thread's stack + TLS — two unsynchronised heap frees that
    # trip a corruption abort ("malloc_consolidate(): unaligned fastbin chunk").
    # Those background threads include scipy/numpy's OpenBLAS pool, spawned the first
    # time the spatial brush builds its KD-tree. The event loop has returned and the
    # app owns no unsaved state, so skip the racy teardown entirely and let the OS
    # reclaim the process. (Confirmed from a core dump: thread in _dl_deallocate_tls,
    # main thread in __run_exit_handlers → libQt6ShaderTools.)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(rc)


if __name__ == "__main__":
    sys.exit(main())
