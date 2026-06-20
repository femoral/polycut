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
from PySide6.QtCore import Property, QObject, Signal, Slot
from PySide6.QtGui import QVector3D

from polycut.bridge.buffer_source import BufferSource
from polycut.core.brush import SpatialBrush
from polycut.core.parts import UNASSIGNED_ID, Partition
from polycut.core.picking import add_to_part, colour_wand, pick_face, screen_ray
from polycut.core.segment import apply_clusters, colour_clusters
from polycut.core.viewport import build_highlight_buffers, build_part_buffers, build_part_chunks

TOOLS = ("cluster", "wand", "brush")  # auto-split, magic wand, spatial brush

# The Colour↔Locality control is a 0..1 weight; this maps its locality end to the
# cluster's internal λ (ADR-0008), scaled so a full slider clearly dominates colour
# (Lab spans ~100) and lands the lamp's top/ring/base. Never shown to the user as λ.
LOCALITY_SCALE = 200.0
DEFAULT_LOCALITY = 0.35  # a modest default — real spatial influence, colour still leads


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
        # The flat-colour Parts buffer and the active-Part silhouette flow through the
        # one shared buffer-source seam: each is armed with a lazy builder, and a carve
        # or selection change re-arms it (drops the memo) so the next read rebuilds.
        # Built on the GUI thread (an on-thread lazy build is allowed by the seam).
        self._parts_source = BufferSource(self)
        self._highlight_source = BufferSource(self)
        self._chunks = None  # cached per-Part explode chunks; rebuilt once per carve
        self._chunk_sources = []  # one buffer-source per chunk, rebuilt with the chunks
        self._last_brush_point = None  # previous brush hit in a drag, for stroke fill-in
        self._active_part = UNASSIGNED_ID  # edits target the remainder until a Part exists
        self._active_tool = "cluster"  # the first manual tool in the panel
        self._cluster_k = 2  # split_by_colour's default
        self._locality = DEFAULT_LOCALITY  # Colour↔Locality weight (0 colour … 1 locality)
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

    def _get_locality(self) -> float:
        return self._locality

    def _set_locality(self, value: float) -> None:
        """The Colour↔Locality slider position, clamped to [0, 1] — 0 is pure colour
        (today's behaviour), 1 is maximum spatial locality (ADR-0008)."""
        value = max(0.0, min(1.0, float(value)))
        if value != self._locality:
            self._locality = value
            self.toolParamsChanged.emit()

    locality = Property(float, _get_locality, _set_locality, notify=toolParamsChanged)

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
        locality = self._locality * LOCALITY_SCALE  # snapshot the control on the GUI thread

        def work() -> None:
            try:
                clusters = colour_clusters(mesh, texture, scope_faces, k, locality)
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

    # ---- flat-colour Parts + highlight buffer sources ------------------
    # The flat-colour Parts view (each face in its Part's swatch colour) and the
    # active-Part silhouette (#30, drawn flat into a mask whose screen-space edge
    # becomes the teal contour) both flow through the one shared buffer-source seam.
    # A carve / selection / visibility change re-arms the sources (drops their memo);
    # the next read rebuilds once, which is why no per-property cache is needed.
    def _invalidate_geometry(self) -> None:
        """Re-arm the Parts + highlight buffer sources and drop the cached explode
        chunks, so the next read of each rebuilds against the current carve/selection."""
        self._chunks = None  # the explode chunks are rebuilt on the next carve
        self._chunk_sources = []  # their per-chunk sources rebuild alongside them
        self._parts_source.bind(self._build_parts)  # re-arm → the adapter re-uploads
        self._highlight_source.bind(self._build_highlight)
        self.geometryChanged.emit()  # the explode chunk count / nodes still read here

    def _build_parts(self):
        """Build the flat-colour Parts buffer (position + per-vertex RGBA) for the
        current carve, or ``None`` before a mesh is bound. Run lazily on the GUI thread
        when the source is first read after a re-arm."""
        if self._mesh is None or self._partition is None:
            return None
        return build_part_buffers(self._mesh, self._partition, self._active_part)

    def _build_highlight(self):
        """Build the active Part's silhouette faces (position-only), or ``None`` when
        Unassigned is the edit target — the contour stands down for the remainder.
        Topology-independent, so it reads even on the half-disconnected Meshy cut."""
        if self._mesh is None or not self._has_highlight():
            return None
        face_ids = (self._partition.labels == self._active_part).nonzero()[0]
        return build_highlight_buffers(self._mesh, face_ids)

    def _get_parts_source(self) -> BufferSource:
        """The flat-colour Parts buffer source the viewport's parts-mode node binds."""
        return self._parts_source

    partsSource = Property(QObject, _get_parts_source, constant=True)

    def _get_highlight_source(self) -> BufferSource:
        """The active-Part silhouette buffer source the contour pass binds."""
        return self._highlight_source

    highlightSource = Property(QObject, _get_highlight_source, constant=True)

    # ---- per-Part explode chunks (#31) ---------------------------------
    # The momentary explode draws the simplified mesh as one node per Part, each
    # translated by its radial offset × the live amount. The chunks are built once per
    # carve and cached (no per-tick buffer re-upload); each chunk's upload buffer flows
    # through its own buffer-source (the same shared seam the mesh/parts nodes use), so
    # the explode Repeater binds the one generic adapter per chunk. The node-placement
    # values (count, offset, swatch colour, id) stay as direct reads — they are not
    # upload data. Each chunk reuses the fused normals/UVs, shading like the mesh.
    def _ensure_chunks(self) -> list:
        if self._chunks is None and self._mesh is not None and self._partition is not None:
            self._chunks = build_part_chunks(self._mesh, self._partition)
            self._chunk_sources = [self._chunk_source(c) for c in self._chunks]
        return self._chunks or []

    def _chunk_source(self, chunk) -> BufferSource:
        """A buffer-source pre-loaded with one chunk's already-built upload buffer."""
        source = BufferSource(self)
        source.update(chunk.buffers)  # pre-built push (built on this GUI thread)
        return source

    def _get_chunk_count(self) -> int:
        return len(self._ensure_chunks())

    chunkCount = Property(int, _get_chunk_count, notify=geometryChanged)

    @Slot(int, result=QObject)
    def chunkSource(self, index: int) -> QObject:
        """The chunk's buffer-source — the explode Repeater binds the generic adapter
        to it, with the triangles/lines topology set on the adapter per pass."""
        self._ensure_chunks()
        return self._chunk_sources[index]

    @Slot(int, result=int)
    def chunkPartId(self, index: int) -> int:
        return int(self._ensure_chunks()[index].part_id)

    @Slot(int, result=QVector3D)
    def chunkOffset(self, index: int) -> QVector3D:
        """The chunk's radial spread direction; the viewport scales it by ``amount``."""
        return QVector3D(*self._ensure_chunks()[index].offset)

    @Slot(int, result="QVariantList")
    def chunkColour(self, index: int) -> list:
        """The chunk's Part swatch RGB — the flat colour the parts render mode draws."""
        return [int(c) for c in self._ensure_chunks()[index].colour]
