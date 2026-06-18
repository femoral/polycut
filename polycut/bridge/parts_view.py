"""The Parts view-model — the observable bridge QML's Parts panel binds to.

Headless `core` (slices A–E) owns the Part data model, the colour clustering, the
ray pick, the wand and the brush; this object is the thin Qt projection of that onto
QML. It holds the current simplified mesh + baked texture and a
:class:`~polycut.core.parts.Partition` over them, and surfaces:

* the **outliner rows** (one per Part: id, name, colour swatch, face count,
  visibility) plus the running total;
* the **active Part** edits target, and the faces it owns (the highlight set);
* the **active tool** (cluster / wand / brush) and its params;
* a **pick** slot: QML hands it a screen click + camera, it builds the world ray in
  ``core`` (:func:`~polycut.core.picking.screen_ray`), resolves the face
  (:func:`~polycut.core.picking.pick_face`), and applies the active tool there.

A fresh cut **rebinds** the view-model, which drops every Part — the state the
"re-cutting clears Parts" warning (G) reads. All geometry stays in ``core``; this
object only marshals and notifies.
"""

from __future__ import annotations

import threading

import numpy as np
from PySide6.QtCore import Property, QByteArray, QObject, Signal, Slot
from PySide6.QtGui import QVector3D

from polycut.core.brush import SpatialBrush
from polycut.core.parts import UNASSIGNED_ID, Partition
from polycut.core.picking import add_to_part, colour_wand, pick_face, screen_ray
from polycut.core.segment import apply_clusters, colour_clusters
from polycut.core.viewport import build_highlight_buffers, build_part_buffers

TOOLS = ("cluster", "wand", "brush")  # auto-split, magic wand, spatial brush


class PartsViewModel(QObject):
    partsChanged = Signal()  # rows / total / hasParts moved
    activePartChanged = Signal()  # the edit target moved
    activeToolChanged = Signal()  # cluster / wand / brush switched
    toolParamsChanged = Signal()  # K / threshold / global / radius moved
    highlightChanged = Signal()  # the active Part's face set (the viewport overlay) moved
    geometryChanged = Signal()  # the flat-colour Parts buffer moved (a carve / visibility)
    clusteringChanged = Signal()  # a cluster started / landed (drives the chip + input gate)
    _clusterReady = Signal(object)  # internal: a worker's cluster result, queued to the GUI thread

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        # The cluster's k-means runs on a worker; its result is delivered back here as
        # a queued signal, so the relabel is applied on the GUI thread (#29). Cross-
        # thread emit → Qt's auto-connection queues it onto this object's event loop.
        self._clustering = False
        self._clusterReady.connect(self._finish_cluster)
        self._mesh = None
        self._texture = None
        self._partition: Partition | None = None
        self._brush: SpatialBrush | None = None  # centroid KD-tree, rebuilt per mesh
        self._buffers = None  # cached flat-colour Parts buffer; rebuilt lazily on carve
        self._highlight_buffers = None  # cached active-Part outline; rebuilt with the highlight
        self._last_brush_point = None  # previous brush hit in a drag, for stroke fill-in
        self._active_part = UNASSIGNED_ID  # edits target the remainder until a Part exists
        self._active_tool = "cluster"  # the first manual tool in the panel
        self._cluster_k = 2  # split_by_colour's default
        self._wand_threshold = 10.0  # CIELAB distance the wand counts as "similar"
        self._wand_global = False  # local (contiguous) wand by default
        self._brush_radius = 0.0  # set from the model's scale by QML before painting

    def rebind(self, mesh, texture) -> None:
        """Bind to a (simplified) mesh + its baked texture, starting a fresh partition
        with every face in Unassigned. Called on each settled cut, so it also clears
        any Parts carved against the previous mesh."""
        self._mesh = mesh
        self._texture = texture
        self._partition = Partition.fresh(face_count=len(mesh.faces))
        self._brush = SpatialBrush(mesh)  # built once per cut; brush drags reuse it
        self._active_part = UNASSIGNED_ID
        self._invalidate_geometry()
        self.partsChanged.emit()
        self.activePartChanged.emit()
        self.highlightChanged.emit()

    def export_partition(self) -> Partition | None:
        """The live partition the exporter must mirror, so the ``.dae`` carries the
        carved Parts (#19 story 18: preview == export). ``None`` until a mesh is
        bound, in which case export falls back to its single-group writer. Its labels
        index the bound (simplified) mesh's faces — the same geometry export writes."""
        return self._partition

    @Slot(result=int)
    def createPart(self) -> int:
        """Add an empty Part, make it the active edit target, and return its id.
        A no-op (``-1``) before a mesh is bound — nothing to carve yet."""
        if self._partition is None:
            return -1
        user_parts = sum(1 for p in self._partition.parts if p.id != UNASSIGNED_ID)
        part_id = self._partition.create_part(name=f"Part {user_parts + 1}")
        self._active_part = part_id
        self._invalidate_geometry()  # the new Part becomes the highlighted target
        self.partsChanged.emit()
        self.activePartChanged.emit()
        self.highlightChanged.emit()
        return part_id

    @Slot()
    def deletePart(self) -> None:
        """Delete the active Part, folding its faces back into Unassigned and
        resetting the edit target to the remainder. A no-op when Unassigned is active
        — the remainder is permanent and can never be dropped."""
        if self._partition is None or self._active_part == UNASSIGNED_ID:
            return
        self._partition.delete(self._active_part)
        self._active_part = UNASSIGNED_ID
        self._invalidate_geometry()
        self.partsChanged.emit()
        self.activePartChanged.emit()
        self.highlightChanged.emit()

    # ---- active Part + its highlight -----------------------------------
    def _get_active_part(self) -> int:
        return self._active_part

    def _set_active_part(self, value: int) -> None:
        value = int(value)
        if value == self._active_part or self._partition is None:
            return
        if value not in {p.id for p in self._partition.parts}:
            return  # only existing Parts are selectable
        self._active_part = value
        self._invalidate_geometry()  # the selection highlight follows the active Part
        self.activePartChanged.emit()
        self.highlightChanged.emit()

    activePartId = Property(int, _get_active_part, _set_active_part, notify=activePartChanged)

    def _get_highlight_faces(self) -> list:
        """The active Part's face ids — the set the viewport highlights (#11)."""
        if self._partition is None:
            return []
        return [int(f) for f in (self._partition.labels == self._active_part).nonzero()[0]]

    highlightFaces = Property("QVariantList", _get_highlight_faces, notify=highlightChanged)

    def _has_highlight(self) -> bool:
        """Whether the active Part should be outlined across the render modes (#30) —
        any real Part, but never the Unassigned remainder."""
        return self._partition is not None and self._active_part != UNASSIGNED_ID

    hasHighlight = Property(bool, _has_highlight, notify=highlightChanged)

    @Slot(int, str)
    def renamePart(self, part_id: int, name: str) -> None:
        """Rename a Part, leaving its face ownership untouched."""
        self._partition.rename(int(part_id), name)
        self.partsChanged.emit()

    @Slot(int, bool)
    def setPartVisible(self, part_id: int, visible: bool) -> None:
        """Show or hide a Part, leaving its face ownership untouched."""
        self._partition.set_visible(int(part_id), bool(visible))
        self._invalidate_geometry()  # hidden Parts blend away in the flat-colour view
        self.partsChanged.emit()

    # ---- active tool + params ------------------------------------------
    def _get_active_tool(self) -> str:
        return self._active_tool

    def _set_active_tool(self, value: str) -> None:
        if value in TOOLS and value != self._active_tool:
            self._active_tool = value
            self.activeToolChanged.emit()

    activeTool = Property(str, _get_active_tool, _set_active_tool, notify=activeToolChanged)

    def _get_cluster_k(self) -> int:
        return self._cluster_k

    def _set_cluster_k(self, value: int) -> None:
        value = int(value)
        if value != self._cluster_k:
            self._cluster_k = value
            self.toolParamsChanged.emit()

    clusterK = Property(int, _get_cluster_k, _set_cluster_k, notify=toolParamsChanged)

    def _get_wand_threshold(self) -> float:
        return self._wand_threshold

    def _set_wand_threshold(self, value: float) -> None:
        value = float(value)
        if value != self._wand_threshold:
            self._wand_threshold = value
            self.toolParamsChanged.emit()

    wandThreshold = Property(float, _get_wand_threshold, _set_wand_threshold, notify=toolParamsChanged)

    def _get_wand_global(self) -> bool:
        return self._wand_global

    def _set_wand_global(self, value: bool) -> None:
        value = bool(value)
        if value != self._wand_global:
            self._wand_global = value
            self.toolParamsChanged.emit()

    wandGlobal = Property(bool, _get_wand_global, _set_wand_global, notify=toolParamsChanged)

    def _get_brush_radius(self) -> float:
        return self._brush_radius

    def _set_brush_radius(self, value: float) -> None:
        value = float(value)
        if value != self._brush_radius:
            self._brush_radius = value
            self.toolParamsChanged.emit()

    brushRadius = Property(float, _get_brush_radius, _set_brush_radius, notify=toolParamsChanged)

    # ---- pick + apply the active tool ----------------------------------
    @Slot()
    def beginStroke(self) -> None:
        """Start a fresh brush stroke — the next brush pick stamps a single point
        rather than sweeping from the previous stroke's end."""
        self._last_brush_point = None

    @Slot(float, float, "QVariantList", "QVariantList", "QVariantList", float, float, float, result=int)
    def pick(self, x, y, cam_pos, forward, up, fov_y, width, height) -> int:
        """Resolve the face under a screen click and apply the active tool there.

        QML hands the click pixel ``(x, y)`` and the camera (position, forward + up
        axes, vertical fov, viewport size); ``core`` builds the world ray
        (:func:`screen_ray`) and the nearest hit face (:func:`pick_face`). The active
        tool then carves at that face through A's partition ops. Returns the hit face
        id, or ``-1`` on a miss (an empty click) or while a cluster is in flight."""
        if self._partition is None or self._clustering:
            return -1  # carve input is gated while a cluster runs off-thread (#29)
        origin, direction = screen_ray(cam_pos, forward, up, fov_y, x, y, width, height)
        face = pick_face(self._mesh, origin, direction)
        if face is None:
            return -1
        if self._active_tool == "cluster":  # heavy k-means → worker; relabel on return
            self._start_cluster(int(face))
            return int(face)
        self._apply_tool(int(face))  # wand / brush are cheap — carve synchronously
        self._invalidate_geometry()  # the flat-colour buffer follows the carve
        self.partsChanged.emit()
        self.highlightChanged.emit()  # the active Part's face set may have grown/shrunk
        return int(face)

    def _apply_tool(self, face: int) -> None:
        """Carve at ``face`` with the active synchronous tool: the brush paints its
        proximity sphere, the wand grows by colour. (The cluster runs off the GUI
        thread — see :meth:`_start_cluster`.)"""
        partition, mesh, texture = self._partition, self._mesh, self._texture
        if self._active_tool == "brush":
            hit = mesh.triangles_center[face]
            self._brush.paint(partition, self._stroke_points(hit), self._brush_radius, self._active_part)
            self._last_brush_point = hit
        else:  # wand — grow by colour
            mode = "global" if self._wand_global else "local"
            faces = colour_wand(mesh, texture, seed=face, threshold=self._wand_threshold, mode=mode)
            add_to_part(partition, faces, self._active_part)

    # ---- cluster off the GUI thread (#29) ------------------------------
    def _get_clustering(self) -> bool:
        return self._clustering

    def _set_clustering(self, value: bool) -> None:
        if value != self._clustering:
            self._clustering = value
            self.clusteringChanged.emit()

    clustering = Property(bool, _get_clustering, notify=clusteringChanged)

    def _start_cluster(self, face: int) -> None:
        """Cluster the picked face's Part off the GUI thread. The k-means runs on a
        worker; the relabel comes back through :attr:`_clusterReady` and is applied on
        the GUI thread, so it never races the outliner / buffer reads. ``scope_faces``
        is snapshotted now (cheap), so the worker only does the perceptual maths."""
        scope = int(self._partition.labels[face])
        scope_faces = np.where(self._partition.labels == scope)[0]
        if scope_faces.size == 0:
            return  # nothing to carve (e.g. everything already assigned)
        self._set_clustering(True)
        mesh, texture, k = self._mesh, self._texture, self._cluster_k

        def work() -> None:
            try:
                clusters = colour_clusters(mesh, texture, scope_faces, k)
            except Exception:  # a failed cluster clears the flag without carving
                clusters = None
            self._clusterReady.emit(
                {"mesh": mesh, "scope": scope, "scope_faces": scope_faces,
                 "clusters": clusters, "k": k}
            )

        threading.Thread(target=work, daemon=True).start()

    @Slot(object)
    def _finish_cluster(self, result) -> None:
        """Apply a finished cluster's relabel on the GUI thread, then clear the flag.
        The result is dropped if the bound mesh changed under it (a re-cut rebind
        landed mid-cluster — its face ids would index the wrong mesh)."""
        clusters = result["clusters"]
        if clusters is not None and result["mesh"] is self._mesh and self._partition is not None:
            apply_clusters(
                self._partition, result["scope"], result["scope_faces"], clusters, result["k"]
            )
            self._invalidate_geometry()  # the flat-colour buffer follows the carve
            self.partsChanged.emit()
            self.highlightChanged.emit()
        self._set_clustering(False)

    def _stroke_points(self, hit):
        """Brush samples from the previous hit to ``hit``, so a fast drag paints a
        continuous tube instead of isolated stamps. The first stamp of a stroke (no
        previous point, or no radius set) is just the hit itself; otherwise the
        segment is densified to roughly half-radius steps (capped, so a long stroke
        can't explode the stamp count)."""
        prev = self._last_brush_point
        if prev is None or self._brush_radius <= 0:
            return [hit]
        segment = hit - prev
        distance = float(np.linalg.norm(segment))
        steps = min(256, max(1, int(distance / (self._brush_radius * 0.5))))
        return [prev + segment * (i / steps) for i in range(1, steps + 1)]

    # ---- outliner rows -------------------------------------------------
    def _get_parts_rows(self) -> list:
        if self._partition is None:
            return []
        return [
            {
                "id": p.id,
                "name": p.name,
                "colour": list(p.colour),
                "faceCount": self._partition.face_count(p.id),
                "visible": p.visible,
                "slot": p.material_slot,
            }
            for p in self._partition.parts
        ]

    partsRows = Property("QVariantList", _get_parts_rows, notify=partsChanged)

    def _get_total_face_count(self) -> int:
        return len(self._mesh.faces) if self._mesh is not None else 0

    totalFaceCount = Property(int, _get_total_face_count, notify=partsChanged)

    def _get_has_parts(self) -> bool:
        """True once any Part beyond the permanent Unassigned remainder exists — the
        state the 're-cutting clears Parts' warning gates on."""
        return self._partition is not None and len(self._partition.parts) > 1

    hasParts = Property(bool, _get_has_parts, notify=partsChanged)

    # ---- flat-colour Parts geometry (the "parts" view mode) ------------
    # The viewport's flat-colour mode draws the simplified mesh with each face in
    # its Part's swatch colour. The buffer (positions + per-vertex RGBA) is built in
    # ``core`` and cached here, rebuilt lazily the next time QML reads it after a
    # carve / visibility change — so a brush drag invalidates once, not per query.
    def _invalidate_geometry(self) -> None:
        self._buffers = None
        self._highlight_buffers = None  # the outline follows the same carves/selection
        self.geometryChanged.emit()

    def _ensure_geometry(self):
        if self._buffers is None and self._mesh is not None and self._partition is not None:
            self._buffers = build_part_buffers(self._mesh, self._partition, self._active_part)
        return self._buffers

    def _get_geometry_ready(self) -> bool:
        return self._ensure_geometry() is not None

    geometryReady = Property(bool, _get_geometry_ready, notify=geometryChanged)

    def _get_geometry_stride(self) -> int:
        buffers = self._ensure_geometry()
        return buffers.stride if buffers else 0

    geometryStride = Property(int, _get_geometry_stride, notify=geometryChanged)

    def _get_geometry_bounds_min(self) -> QVector3D:
        buffers = self._ensure_geometry()
        return QVector3D(*buffers.bounds_min) if buffers else QVector3D()

    geometryBoundsMin = Property(QVector3D, _get_geometry_bounds_min, notify=geometryChanged)

    def _get_geometry_bounds_max(self) -> QVector3D:
        buffers = self._ensure_geometry()
        return QVector3D(*buffers.bounds_max) if buffers else QVector3D()

    geometryBoundsMax = Property(QVector3D, _get_geometry_bounds_max, notify=geometryChanged)

    @Slot(result=QByteArray)
    def geometryVertexData(self) -> QByteArray:
        """The interleaved position + RGBA buffer the Parts geometry uploads."""
        buffers = self._ensure_geometry()
        return QByteArray(buffers.vertex_data) if buffers else QByteArray()

    @Slot(result=QByteArray)
    def geometryIndexData(self) -> QByteArray:
        """The triangle index buffer the Parts geometry uploads."""
        buffers = self._ensure_geometry()
        return QByteArray(buffers.index_data) if buffers else QByteArray()

    # ---- active-Part outline overlay (the cross-mode highlight, #30) ----
    # A teal line set of the active Part's edges, drawn over the fused mesh in shaded /
    # edges / wireframe (parts mode keeps its own brighten-toward-white). Reuses the
    # fused mesh's positions so the lines lie on the surface; rebuilt lazily with the
    # highlight and stood down (no buffers) whenever Unassigned is the edit target.
    def _ensure_highlight(self):
        if self._highlight_buffers is None and self._mesh is not None and self._has_highlight():
            face_ids = (self._partition.labels == self._active_part).nonzero()[0]
            self._highlight_buffers = build_highlight_buffers(self._mesh, face_ids)
        return self._highlight_buffers if self._has_highlight() else None

    def _get_highlight_ready(self) -> bool:
        return self._ensure_highlight() is not None

    highlightReady = Property(bool, _get_highlight_ready, notify=highlightChanged)

    def _get_highlight_stride(self) -> int:
        buffers = self._ensure_highlight()
        return buffers.stride if buffers else 0

    highlightStride = Property(int, _get_highlight_stride, notify=highlightChanged)

    def _get_highlight_bounds_min(self) -> QVector3D:
        buffers = self._ensure_highlight()
        return QVector3D(*buffers.bounds_min) if buffers else QVector3D()

    highlightBoundsMin = Property(QVector3D, _get_highlight_bounds_min, notify=highlightChanged)

    def _get_highlight_bounds_max(self) -> QVector3D:
        buffers = self._ensure_highlight()
        return QVector3D(*buffers.bounds_max) if buffers else QVector3D()

    highlightBoundsMax = Property(QVector3D, _get_highlight_bounds_max, notify=highlightChanged)

    @Slot(result=QByteArray)
    def highlightVertexData(self) -> QByteArray:
        """The position-only vertex buffer the outline overlay uploads."""
        buffers = self._ensure_highlight()
        return QByteArray(buffers.vertex_data) if buffers else QByteArray()

    @Slot(result=QByteArray)
    def highlightLineData(self) -> QByteArray:
        """The active Part's edge-index buffer (low→high pairs) for the Lines pass."""
        buffers = self._ensure_highlight()
        return QByteArray(buffers.index_data) if buffers else QByteArray()
