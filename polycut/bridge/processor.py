"""The ``processor`` bridge object QML talks to.

Loads and exports run on worker threads so the 646k-face pipeline never freezes
the UI; results come back as Qt signals (thread-safe, delivered queued on the GUI
thread). The bridge holds the current :class:`SourceModel` and surfaces its stats
as QML properties.
"""

from __future__ import annotations

import platform
import subprocess
import threading
from pathlib import Path

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot

from polycut.core import export_collada, load_source_model


def _to_path(value: str) -> Path:
    """Accept either a plain path or a ``file://`` URL from QML."""
    url = QUrl(value)
    if url.isLocalFile():
        return Path(url.toLocalFile())
    return Path(value)


class Processor(QObject):
    # results
    modelLoaded = Signal()
    loadFailed = Signal(str)
    exportFinished = Signal(str, float, int, int)  # path, sizeBytes, faceCount, textureCount
    exportFailed = Signal(str)

    # state
    statsChanged = Signal()
    busyChanged = Signal()
    statusChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._model = None
        self._busy = False
        self._status = "Awaiting import"

    # ---- busy / status -------------------------------------------------
    def _get_busy(self) -> bool:
        return self._busy

    busy = Property(bool, _get_busy, notify=busyChanged)

    def _set_busy(self, value: bool) -> None:
        if value != self._busy:
            self._busy = value
            self.busyChanged.emit()

    def _get_status(self) -> str:
        return self._status

    status = Property(str, _get_status, notify=statusChanged)

    def _set_status(self, text: str) -> None:
        if text != self._status:
            self._status = text
            self.statusChanged.emit()

    # ---- model stats ---------------------------------------------------
    def _get_has_model(self) -> bool:
        return self._model is not None

    hasModel = Property(bool, _get_has_model, notify=statsChanged)

    def _get_file_name(self) -> str:
        return self._model.source_path.name if self._model else ""

    fileName = Property(str, _get_file_name, notify=statsChanged)

    def _get_face_count(self) -> int:
        return self._model.face_count if self._model else 0

    faceCount = Property(int, _get_face_count, notify=statsChanged)

    def _get_object_count(self) -> int:
        return self._model.object_count if self._model else 0

    objectCount = Property(int, _get_object_count, notify=statsChanged)

    def _get_has_texture(self) -> bool:
        return bool(self._model and self._model.has_texture)

    hasTexture = Property(bool, _get_has_texture, notify=statsChanged)

    def _get_texture_name(self) -> str:
        if self._model and self._model.has_texture:
            return self._model.texture_path.name
        return ""

    textureName = Property(str, _get_texture_name, notify=statsChanged)

    def _get_default_export_path(self) -> str:
        if not self._model:
            return ""
        return str(self._model.source_path.with_suffix(".dae"))

    defaultExportPath = Property(str, _get_default_export_path, notify=statsChanged)

    # ---- load ----------------------------------------------------------
    @Slot(str)
    def loadFile(self, path: str) -> None:
        source = _to_path(path)
        self._set_status(f"Loading {source.name}…")
        self._set_busy(True)
        threading.Thread(target=self._load_worker, args=(source,), daemon=True).start()

    def _load_worker(self, source: Path) -> None:
        try:
            model = load_source_model(source)
        except Exception as exc:  # surfaced to the user, never swallowed
            self._set_busy(False)
            self._set_status("Awaiting import")
            self.loadFailed.emit(str(exc))
            return
        self._model = model
        self._set_busy(False)
        self._set_status(f"Loaded {source.name}")
        self.statsChanged.emit()
        self.modelLoaded.emit()

    # ---- export --------------------------------------------------------
    @Slot(str)
    def exportModel(self, output_path: str) -> None:
        if self._model is None:
            self.exportFailed.emit("No model loaded")
            return
        out = _to_path(output_path)
        self._set_status("Exporting to SketchUp…")
        self._set_busy(True)
        threading.Thread(target=self._export_worker, args=(out,), daemon=True).start()

    def _export_worker(self, out: Path) -> None:
        try:
            result = export_collada(self._model, out)
        except Exception as exc:
            self._set_busy(False)
            self._set_status("Export failed")
            self.exportFailed.emit(str(exc))
            return
        self._set_busy(False)
        self._set_status(f"Exported {result.output_path.name}")
        self.exportFinished.emit(
            str(result.output_path),
            float(result.output_size_bytes),
            result.face_count,
            result.texture_count,
        )

    # ---- reveal --------------------------------------------------------
    @Slot(str)
    def revealInExplorer(self, path: str) -> None:
        target = _to_path(path)
        if not target.exists():
            target = target.parent
        _reveal(target)


def _reveal(target: Path) -> None:
    """Open the platform file manager focused on ``target``."""
    system = platform.system()
    try:
        if system == "Windows":
            if target.is_dir():
                subprocess.run(["explorer", str(target)], check=False)
            else:
                subprocess.run(["explorer", "/select,", str(target)], check=False)
        elif system == "Darwin":
            arg = "-R" if target.is_file() else None
            subprocess.run(["open", *( [arg] if arg else [] ), str(target)], check=False)
        else:  # Linux / other: open the containing folder
            folder = target if target.is_dir() else target.parent
            subprocess.run(["xdg-open", str(folder)], check=False)
    except OSError:
        pass  # reveal is a convenience; never crash the app over it
