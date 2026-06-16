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

from polycut.bridge.mesh_view import MeshView
from polycut.core import (
    ModelSimplifier,
    build_mesh_buffers,
    export_collada,
    load_source_model,
    scale_factor,
    scale_geometry,
)
from polycut.core.scale import UNIT_METERS, UNIT_NAMES

DEFAULT_REDUCTION = 0.25  # keep ~25% of faces — the −75% default applied on load
MIN_FACES = 100  # floor so the slider can't collapse the mesh to nothing
RENDER_MODES = ("shaded", "edges", "wireframe")  # viewport shading modes (#9)


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
    simplifyFinished = Signal()
    simplifyFailed = Signal(str)
    exportFinished = Signal(str, float, int, int)  # path, sizeBytes, faceCount, textureCount
    exportFailed = Signal(str)

    # state
    statsChanged = Signal()
    busyChanged = Signal()
    statusChanged = Signal()
    scaleChanged = Signal()
    simplifyingChanged = Signal()
    renderModeChanged = Signal()
    selectionChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._model = None  # the loaded original (source for re-simplify)
        self._simplified = None  # current decimated model; what export writes
        self._target = 0  # requested target face count
        # The two mesh views the before/after split draws (#10): the original is
        # fed once on load and renders immediately; the simplified is refreshed
        # off-thread each time a cut settles. Render is decoupled from the cut
        # (ADR-0003) — the viewport never blocks on the CPU collapse.
        self._original_mesh = MeshView(self)
        self._simplified_mesh = MeshView(self)
        # The OBJ parsed into PyMeshLab once per model; re-cut from memory on each
        # settle (#18). Built + disposed only on the serialized simplify worker, so
        # PyMeshLab is never touched from two threads. _simplifier_model records
        # which model it holds, so opening another model rebuilds and disposes it.
        self._simplifier = None
        self._simplifier_model = None
        self._busy = False
        self._simplifying = False  # a faithful cut is in flight → on-canvas chip
        self._status = "Awaiting import"
        self._render_mode = "shaded"  # viewport shading: shaded | edges | wireframe
        self._selected_index = -1  # selected outliner row; -1 until a model loads
        # PyMeshLab is not thread-safe — serialize decimations. _pending_target
        # holds the latest requested target; one worker drains it, coalescing
        # rapid slider releases so only the most recent target actually runs.
        self._simplify_guard = threading.Lock()
        self._pending_target = None
        self._simplify_active = False
        # scale + units — baked into the geometry at export, target unit declared
        self._scale_multiplier = 1.0
        self._source_unit = "m"
        self._target_unit = "m"

    def _current(self):
        """The model the UI reflects and export writes: simplified if present."""
        return self._simplified or self._model

    # ---- busy / status -------------------------------------------------
    def _get_busy(self) -> bool:
        return self._busy

    busy = Property(bool, _get_busy, notify=busyChanged)

    def _set_busy(self, value: bool) -> None:
        if value != self._busy:
            self._busy = value
            self.busyChanged.emit()

    def _get_simplifying(self) -> bool:
        return self._simplifying

    simplifying = Property(bool, _get_simplifying, notify=simplifyingChanged)

    def _set_simplifying(self, value: bool) -> None:
        if value != self._simplifying:
            self._simplifying = value
            self.simplifyingChanged.emit()

    # ---- render mode (Shaded / Wireframe / Edges, #9) ------------------
    def _get_render_mode(self) -> str:
        return self._render_mode

    def _set_render_mode(self, value: str) -> None:
        if value in RENDER_MODES and value != self._render_mode:
            self._render_mode = value
            self.renderModeChanged.emit()

    renderMode = Property(
        str, _get_render_mode, _set_render_mode, notify=renderModeChanged
    )

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

    def _get_original_mesh(self) -> MeshView:
        """The original full-res mesh — fed on load, the before side (#10)."""
        return self._original_mesh

    originalMesh = Property(QObject, _get_original_mesh, constant=True)

    def _get_simplified_mesh(self) -> MeshView:
        """The simplified (after) side — the exact mesh the exporter writes (#10)."""
        return self._simplified_mesh

    simplifiedMesh = Property(QObject, _get_simplified_mesh, constant=True)

    def _get_file_name(self) -> str:
        return self._model.source_path.name if self._model else ""

    fileName = Property(str, _get_file_name, notify=statsChanged)

    def _get_face_count(self) -> int:
        """The current (post-simplify) face count — the hero readout."""
        current = self._current()
        return current.face_count if current else 0

    faceCount = Property(int, _get_face_count, notify=statsChanged)

    def _get_original_face_count(self) -> int:
        return self._model.face_count if self._model else 0

    originalFaceCount = Property(int, _get_original_face_count, notify=statsChanged)

    def _get_target_face_count(self) -> int:
        return self._target

    targetFaceCount = Property(int, _get_target_face_count, notify=statsChanged)

    def _get_reduction_percent(self) -> int:
        """How much the mesh has shrunk from the original, for the −NN% badge."""
        if not self._model or self._model.face_count == 0:
            return 0
        return round((1 - self._get_face_count() / self._model.face_count) * 100)

    reductionPercent = Property(int, _get_reduction_percent, notify=statsChanged)

    def _get_object_count(self) -> int:
        return self._model.object_count if self._model else 0

    objectCount = Property(int, _get_object_count, notify=statsChanged)

    def _get_outliner_objects(self) -> list:
        """The Scene Outliner rows — one per object in the loaded file (#11)."""
        if not self._model:
            return []
        return [
            {"name": obj.name, "faceCount": obj.face_count}
            for obj in self._model.objects
        ]

    outlinerObjects = Property(
        "QVariantList", _get_outliner_objects, notify=statsChanged
    )

    def _get_selected_index(self) -> int:
        return self._selected_index

    def _set_selected_index(self, value: int) -> None:
        value = int(value)
        if value == self._selected_index:
            return
        if not 0 <= value < len(self._model.objects if self._model else ()):
            return  # only existing rows are selectable
        self._selected_index = value
        self.selectionChanged.emit()

    selectedObjectIndex = Property(
        int, _get_selected_index, _set_selected_index, notify=selectionChanged
    )

    def _get_selected_name(self) -> str:
        """The selected object's name, for the status bar's 'Selected: <object>'."""
        if not self._model or not 0 <= self._selected_index < len(self._model.objects):
            return ""
        return self._model.objects[self._selected_index].name

    selectedObjectName = Property(str, _get_selected_name, notify=selectionChanged)

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
        self._simplified = None  # show the original until the default reduction lands
        self._selected_index = 0 if model.objects else -1  # select the first object
        self.selectionChanged.emit()
        self._feed_mesh_view(self._original_mesh, model)  # original renders at once
        self._target = self._clamp_target(round(model.face_count * DEFAULT_REDUCTION))
        self._set_busy(False)
        self._set_status(f"Loaded {source.name}")
        self.statsChanged.emit()
        self.scaleChanged.emit()  # refresh the size readout for the new model
        self.modelLoaded.emit()
        self.simplify(self._target)  # apply the default −75% reduction

    # ---- simplify ------------------------------------------------------
    @Slot(int)
    def simplify(self, target_faces: int) -> None:
        if self._model is None:
            return
        self._target = self._clamp_target(int(target_faces))
        self._set_status("Simplifying…")
        self._set_busy(True)
        self._set_simplifying(True)  # after-side dims + shows the teal chip
        self.statsChanged.emit()  # reflect the new target on the input immediately
        with self._simplify_guard:
            self._pending_target = self._target
            if self._simplify_active:
                return  # a worker is running — it will pick up this latest target
            self._simplify_active = True
        threading.Thread(target=self._simplify_loop, daemon=True).start()

    def _simplify_loop(self) -> None:
        """Drain pending targets one at a time; never two decimations at once."""
        while True:
            with self._simplify_guard:
                target = self._pending_target
                self._pending_target = None
                if target is None:
                    self._simplify_active = False
                    return

            try:
                simplified = self._simplifier_for(self._model).simplify(target)
            except Exception as exc:
                self._dispose_simplifier()
                with self._simplify_guard:
                    self._simplify_active = False
                    self._pending_target = None
                self._set_busy(False)
                self._set_simplifying(False)
                self._set_status("Simplify failed")
                self.simplifyFailed.emit(str(exc))
                return

            self._simplified = simplified
            with self._simplify_guard:
                if self._pending_target is not None:
                    continue  # a newer target arrived mid-run — serve it next
                self._simplify_active = False
            self._refresh_mesh_view(simplified)  # feed the viewport off-thread
            self._set_busy(False)
            self._set_simplifying(False)  # fresh mesh swapped in — chip clears
            self._set_status(f"Simplified to {simplified.face_count:,} faces")
            self.statsChanged.emit()
            self.scaleChanged.emit()  # the size readout follows the new geometry
            self.simplifyFinished.emit()
            return

    def _refresh_mesh_view(self, model) -> None:
        """Feed the simplified (after) side with ``model``'s render buffers."""
        self._feed_mesh_view(self._simplified_mesh, model)

    def _feed_mesh_view(self, view, model) -> None:
        """Rebuild ``model``'s render buffers and hand them to ``view``.

        Runs off the GUI thread, so the (numpy) interleave never hitches it. The
        texture follows the model — empty URL when none was found. The viewport is
        a non-critical projection: if building its buffers fails, the prior mesh
        stays on screen and the load → export flow is untouched.
        """
        try:
            buffers = build_mesh_buffers(model)
        except Exception:  # viewport is secondary — never break simplify/export
            return
        texture = model.texture_path
        url = QUrl.fromLocalFile(str(texture)) if texture else QUrl()
        view.update(buffers, url)

    def _clamp_target(self, target: int) -> int:
        """Keep the target within [floor, original] — no up-sampling, no zero. The
        floor is MIN_FACES, but never above the model's own size: a model already
        below MIN_FACES clamps to its face count, not up past it (which drove the
        slider's reduction badge negative)."""
        if not self._model:
            return max(MIN_FACES, target)
        floor = min(MIN_FACES, self._model.face_count)
        return max(floor, min(target, self._model.face_count))

    def _simplifier_for(self, model):
        """The loaded simplifier for ``model``, parsing once and disposing the
        previous model's on a model switch. Called only from the simplify worker."""
        if self._simplifier is None or self._simplifier_model is not model:
            self._dispose_simplifier()
            self._simplifier = ModelSimplifier(model)
            self._simplifier_model = model
        return self._simplifier

    def _dispose_simplifier(self) -> None:
        """Release the loaded mesh held for the previous model — no leak, no stale
        geometry when another model is opened."""
        if self._simplifier is not None:
            self._simplifier.close()
        self._simplifier = None
        self._simplifier_model = None

    # ---- scale + units -------------------------------------------------
    def _get_units(self) -> list:
        return list(UNIT_METERS.keys())

    units = Property("QVariantList", _get_units, constant=True)

    def _get_scale_multiplier(self) -> float:
        return self._scale_multiplier

    def _set_scale_multiplier(self, value: float) -> None:
        value = float(value)
        if value > 0 and value != self._scale_multiplier:
            self._scale_multiplier = value
            self.scaleChanged.emit()

    scaleMultiplier = Property(
        float, _get_scale_multiplier, _set_scale_multiplier, notify=scaleChanged
    )

    def _get_source_unit(self) -> str:
        return self._source_unit

    def _set_source_unit(self, value: str) -> None:
        if value in UNIT_METERS and value != self._source_unit:
            self._source_unit = value
            self.scaleChanged.emit()

    sourceUnit = Property(str, _get_source_unit, _set_source_unit, notify=scaleChanged)

    def _get_target_unit(self) -> str:
        return self._target_unit

    def _set_target_unit(self, value: str) -> None:
        if value in UNIT_METERS and value != self._target_unit:
            self._target_unit = value
            self.scaleChanged.emit()

    targetUnit = Property(str, _get_target_unit, _set_target_unit, notify=scaleChanged)

    def _get_scaled_dimensions(self) -> str:
        """The model's resulting real-world size in the target unit — the §7 delta."""
        model = self._current()
        if model is None:
            return ""
        factor = scale_factor(self._scale_multiplier, self._source_unit, self._target_unit)
        lo, hi = model.geometry.bounds
        ext = (hi - lo) * factor
        return f"{ext[0]:.3g} × {ext[1]:.3g} × {ext[2]:.3g} {self._target_unit}"

    scaledDimensions = Property(str, _get_scaled_dimensions, notify=scaleChanged)

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
            model = self._current()
            factor = scale_factor(
                self._scale_multiplier, self._source_unit, self._target_unit
            )
            if factor != 1.0:
                model = scale_geometry(model, factor)
            result = export_collada(
                model,
                out,
                unit_name=UNIT_NAMES[self._target_unit],
                unit_meters=UNIT_METERS[self._target_unit],
            )
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
