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

from PySide6.QtCore import Property, QObject, Signal, Slot

from polycut.core.brush import SpatialBrush
from polycut.core.parts import UNASSIGNED_ID, Partition
from polycut.core.picking import add_to_part, colour_wand, pick_face, screen_ray
from polycut.core.segment import split_by_colour

TOOLS = ("cluster", "wand", "brush")  # auto-split, magic wand, spatial brush


class PartsViewModel(QObject):
    partsChanged = Signal()  # rows / total / hasParts moved
    activePartChanged = Signal()  # the edit target moved
    activeToolChanged = Signal()  # cluster / wand / brush switched
    toolParamsChanged = Signal()  # K / threshold / global / radius moved
    highlightChanged = Signal()  # the active Part's face set (the viewport overlay) moved

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._mesh = None
        self._texture = None
        self._partition: Partition | None = None
        self._brush: SpatialBrush | None = None  # centroid KD-tree, rebuilt per mesh
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
        self.partsChanged.emit()
        self.activePartChanged.emit()
        self.highlightChanged.emit()

    @Slot(result=int)
    def createPart(self) -> int:
        """Add an empty Part, make it the active edit target, and return its id."""
        user_parts = sum(1 for p in self._partition.parts if p.id != UNASSIGNED_ID)
        part_id = self._partition.create_part(name=f"Part {user_parts + 1}")
        self._active_part = part_id
        self.partsChanged.emit()
        self.activePartChanged.emit()
        self.highlightChanged.emit()
        return part_id

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
        self.activePartChanged.emit()
        self.highlightChanged.emit()

    activePartId = Property(int, _get_active_part, _set_active_part, notify=activePartChanged)

    def _get_highlight_faces(self) -> list:
        """The active Part's face ids — the set the viewport highlights (#11)."""
        if self._partition is None:
            return []
        return [int(f) for f in (self._partition.labels == self._active_part).nonzero()[0]]

    highlightFaces = Property("QVariantList", _get_highlight_faces, notify=highlightChanged)

    @Slot(int, str)
    def renamePart(self, part_id: int, name: str) -> None:
        """Rename a Part, leaving its face ownership untouched."""
        self._partition.rename(int(part_id), name)
        self.partsChanged.emit()

    @Slot(int, bool)
    def setPartVisible(self, part_id: int, visible: bool) -> None:
        """Show or hide a Part, leaving its face ownership untouched."""
        self._partition.set_visible(int(part_id), bool(visible))
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
    @Slot(float, float, "QVariantList", "QVariantList", "QVariantList", float, float, float, result=int)
    def pick(self, x, y, cam_pos, forward, up, fov_y, width, height) -> int:
        """Resolve the face under a screen click and apply the active tool there.

        QML hands the click pixel ``(x, y)`` and the camera (position, forward + up
        axes, vertical fov, viewport size); ``core`` builds the world ray
        (:func:`screen_ray`) and the nearest hit face (:func:`pick_face`). The active
        tool then carves at that face through A's partition ops. Returns the hit face
        id, or ``-1`` on a miss (an empty click)."""
        if self._partition is None:
            return -1
        origin, direction = screen_ray(cam_pos, forward, up, fov_y, x, y, width, height)
        face = pick_face(self._mesh, origin, direction)
        if face is None:
            return -1
        self._apply_tool(int(face))
        self.partsChanged.emit()
        self.highlightChanged.emit()  # the active Part's face set may have grown/shrunk
        return int(face)

    def _apply_tool(self, face: int) -> None:
        """Carve at ``face`` with the active tool: the brush paints its proximity
        sphere, the wand grows by colour, the cluster splits the picked face's Part."""
        partition, mesh, texture = self._partition, self._mesh, self._texture
        if self._active_tool == "brush":
            hit = mesh.triangles_center[face]
            self._brush.paint(partition, [hit], self._brush_radius, self._active_part)
        elif self._active_tool == "wand":
            mode = "global" if self._wand_global else "local"
            faces = colour_wand(mesh, texture, seed=face, threshold=self._wand_threshold, mode=mode)
            add_to_part(partition, faces, self._active_part)
        else:  # cluster — subdivide the Part the picked face belongs to
            scope = int(partition.labels[face])
            split_by_colour(partition, mesh, texture, k=self._cluster_k, scope=scope)

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
