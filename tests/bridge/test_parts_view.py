"""The Parts view-model the QML Parts panel binds to (#25, MVP-3 slice F).

The bridge seam between headless `core` (A–E) and QML: an observable
:class:`PartsViewModel` carrying the outliner rows (one per Part: colour, name,
face count, visibility) + running total, the active Part + active tool + its params,
and a ``pick`` slot that turns a screen click + camera into a ``core`` ray, resolves
the face (D), and applies the active tool through A's partition ops. Driven directly
as a QObject — no 3D scene — so these pin the *view-model*, not the pixels (HITL, G).
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import trimesh

from polycut.bridge import processor as processor_module
from polycut.bridge.parts_view import PartsViewModel
from polycut.bridge.processor import Processor
from polycut.core.model import SceneObject, SourceModel

BROWN = (120, 72, 36)
BROWN2 = (130, 82, 46)
GREY = (160, 160, 160)


def _textured_mesh():
    """Six faces over a 3-texel texture [BROWN, BROWN2, GREY], as four disconnected
    islands (faces 0,1 BROWN / 2,3 BROWN / 4 BROWN2 / 5 GREY) — the same soup the
    wand + brush were specced against, so tool application is exercised realistically."""
    texture = np.array([[BROWN, BROWN2, GREY]], dtype=np.uint8)
    quads = [(0, [(0, 1, 2), (0, 2, 3)], 0), (4, [(0, 1, 2), (0, 2, 3)], 0),
             (8, [(0, 1, 2)], 1), (11, [(0, 1, 2)], 2)]
    us = [1 / 6, 1 / 2, 5 / 6]
    verts, faces, uv = [], [], []
    for base, tris, col in quads:
        for k in range(4 if len(tris) == 2 else 3):
            verts.append([base + k, col, 0])
            uv.append([us[col], 0.5])
        for tri in tris:
            faces.append([base + i for i in tri])
    mesh = trimesh.Trimesh(
        vertices=np.array(verts, float), faces=np.array(faces, np.int64),
        visual=trimesh.visual.TextureVisuals(uv=np.array(uv)), process=False,
    )
    return mesh, texture


def _pick_mesh():
    """Three well-separated, pickable triangles in the z=0 plane (faces 0,1,2 centred
    at x = 0, 2, 4), textured BROWN / BROWN / GREY. A top-down camera aimed at a
    centre maps its centre pixel straight onto that face — so tests can click a known
    triangle — while the colours let the wand and cluster tools do real work."""
    centers, cols = [(0.0, 0.0), (2.0, 0.0), (4.0, 0.0)], [0, 0, 2]  # texel idx
    texture = np.array([[BROWN, BROWN2, GREY]], dtype=np.uint8)
    us = [1 / 6, 1 / 2, 5 / 6]
    verts, faces, uv = [], [], []
    for (cx, cy), col in zip(centers, cols):
        base = len(verts)
        verts += [[cx - 0.3, cy - 0.3, 0], [cx + 0.3, cy - 0.3, 0], [cx, cy + 0.4, 0]]
        uv += [[us[col], 0.5]] * 3
        faces.append([base, base + 1, base + 2])
    mesh = trimesh.Trimesh(
        vertices=np.array(verts, float), faces=np.array(faces, np.int64),
        visual=trimesh.visual.TextureVisuals(uv=np.array(uv)), process=False,
    )
    return mesh, texture, centers


def _click(vm, center, w=100, h=100):
    """Click the centre pixel of a viewport whose top-down camera is aimed at
    ``center`` — i.e. drop a ray straight onto the triangle there."""
    cx, cy = center
    return vm.pick(49.5, 49.5, [cx, cy, 5.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0], 60.0, w, h)


def test_rebinding_exposes_a_fresh_partition_of_one_unassigned_row():
    """Binding the view-model to a mesh starts it on a fresh partition: every face
    sits in Unassigned, so there is one row carrying the full face count, the running
    total equals the mesh, and no user Parts exist yet."""
    mesh, texture = _textured_mesh()
    vm = PartsViewModel()

    vm.rebind(mesh, texture)

    assert vm.partsRows == [
        {"id": 0, "name": "Unassigned", "colour": [130, 130, 130], "faceCount": 6, "visible": True}
    ]
    assert vm.totalFaceCount == 6
    assert vm.hasParts is False  # only the permanent remainder; nothing carved yet


def test_creating_a_part_adds_a_row_and_makes_it_active():
    """The '+ New Part' action adds an empty Part, makes it the active edit target,
    and notifies — so the outliner grows a row and subsequent tool strokes land on
    the new Part."""
    mesh, texture = _textured_mesh()
    vm = PartsViewModel()
    vm.rebind(mesh, texture)
    row_counts, actives = [], []
    vm.partsChanged.connect(lambda: row_counts.append(len(vm.partsRows)))
    vm.activePartChanged.connect(lambda: actives.append(vm.activePartId))

    new_id = vm.createPart()

    assert new_id != 0  # a real Part, not the Unassigned remainder
    assert vm.activePartId == new_id  # the new Part becomes the edit target
    assert vm.hasParts is True
    assert [r["name"] for r in vm.partsRows] == ["Unassigned", "Part 1"]
    assert row_counts[-1] == 2  # partsChanged fired with the new row present
    assert actives[-1] == new_id


def test_active_tool_and_params_are_observable_and_notify():
    """The active tool and each tool param are read/write properties that notify on
    change (and not on a no-op write), so QML's tool picker and param controls stay
    in sync without polling."""
    vm = PartsViewModel()
    tools, params = [], []
    vm.activeToolChanged.connect(lambda: tools.append(vm.activeTool))
    vm.toolParamsChanged.connect(lambda: params.append(True))

    vm.activeTool = "brush"
    assert vm.activeTool == "brush"
    vm.activeTool = "brush"  # same value — no churn
    assert tools == ["brush"]

    vm.clusterK = 3
    vm.wandThreshold = 8.0
    vm.wandGlobal = True
    vm.brushRadius = 0.05
    assert (vm.clusterK, vm.wandThreshold, vm.wandGlobal, vm.brushRadius) == (3, 8.0, True, 0.05)
    assert len(params) == 4  # one notification per distinct param change


def test_pick_with_the_brush_resolves_the_face_and_paints_the_active_part():
    """With the brush active, clicking a triangle resolves that face (via the camera
    ray) and paints the swept faces into the active Part — the row's count grows and
    the partition stays exhaustive."""
    mesh, texture, centers = _pick_mesh()
    vm = PartsViewModel()
    vm.rebind(mesh, texture)
    legs = vm.createPart()
    vm.activeTool = "brush"
    vm.brushRadius = 0.5  # reaches only the clicked triangle's own centroid (others are 2 away)

    face = _click(vm, centers[1])  # click the middle triangle

    assert face == 1  # the pick slot resolved the clicked face from the camera + pixel
    rows = {r["id"]: r for r in vm.partsRows}
    assert rows[legs]["faceCount"] == 1  # the brushed face joined the active Part
    assert sum(r["faceCount"] for r in vm.partsRows) == 3  # still exhaustive


def test_pick_with_the_wand_grows_the_active_part_by_colour():
    """With the wand active in global mode, clicking a BROWN triangle grabs every
    BROWN face into the active Part and leaves the GREY one — the param (threshold +
    global) drives the grow, the click only seeds it."""
    mesh, texture, centers = _pick_mesh()
    vm = PartsViewModel()
    vm.rebind(mesh, texture)
    wood = vm.createPart()
    vm.activeTool = "wand"
    vm.wandGlobal = True
    vm.wandThreshold = 10.0

    face = _click(vm, centers[0])  # click a BROWN triangle (face 0)

    assert face == 0
    rows = {r["id"]: r for r in vm.partsRows}
    assert rows[wood]["faceCount"] == 2  # both BROWN faces grabbed; the GREY one excluded
    assert sum(r["faceCount"] for r in vm.partsRows) == 3


def test_pick_with_the_cluster_tool_splits_the_picked_parts_scope_by_colour():
    """With the cluster tool active, clicking a face subdivides the Part that face
    belongs to into K colour clusters. Clicking inside Unassigned carves the whole
    remainder: the two BROWN faces and the GREY one fall into separate Parts."""
    mesh, texture, centers = _pick_mesh()
    vm = PartsViewModel()
    vm.rebind(mesh, texture)
    vm.activeTool = "cluster"
    vm.clusterK = 2

    face = _click(vm, centers[0])  # click a face still in Unassigned

    assert face == 0
    rows = {r["name"]: r for r in vm.partsRows}
    assert rows["Unassigned"]["faceCount"] == 0  # the scope was consumed
    user_counts = sorted(r["faceCount"] for r in vm.partsRows if r["name"] != "Unassigned")
    assert user_counts == [1, 2]  # GREY alone + the two BROWN together
    assert sum(r["faceCount"] for r in vm.partsRows) == 3


def test_selecting_a_part_makes_it_active_and_highlights_its_faces():
    """Choosing a Part in the outliner makes it the active edit target, notifies, and
    exposes that Part's faces as the highlight set the viewport lights up (#11
    selection→highlight, now per Part). Re-selecting the same Part is a no-op."""
    mesh, texture, centers = _pick_mesh()
    vm = PartsViewModel()
    vm.rebind(mesh, texture)
    wood = vm.createPart()
    vm.activeTool = "wand"
    vm.wandGlobal = True
    vm.wandThreshold = 10.0
    _click(vm, centers[0])  # paint the two BROWN faces (0, 1) into wood

    emits = []
    vm.activePartChanged.connect(lambda: emits.append(vm.activePartId))

    vm.activePartId = 0  # select the Unassigned remainder
    assert emits == [0]
    assert set(vm.highlightFaces) == {2}  # Unassigned now holds only the GREY face

    vm.activePartId = wood  # select the wood Part
    assert emits == [0, wood]
    assert set(vm.highlightFaces) == {0, 1}  # its faces light up

    vm.activePartId = wood  # same Part — no churn
    assert emits == [0, wood]


def test_renaming_and_toggling_visibility_round_trip_to_the_rows():
    """Renaming a Part and hiding it flow straight back into the outliner rows and
    notify — the inline-rename field and the eye toggle in G bind to these."""
    mesh, texture, _ = _pick_mesh()
    vm = PartsViewModel()
    vm.rebind(mesh, texture)
    wood = vm.createPart()
    emits = []
    vm.partsChanged.connect(lambda: emits.append(True))

    vm.renamePart(wood, "Frame")
    vm.setPartVisible(wood, False)

    row = {r["id"]: r for r in vm.partsRows}[wood]
    assert row["name"] == "Frame"
    assert row["visible"] is False
    assert len(emits) == 2  # each edit notified once


def test_a_new_cut_rebinds_and_clears_the_parts():
    """A fresh simplify rebinds the view-model to the new mesh, dropping every carved
    Part — the labels were indexed against the old face set. hasParts falling back to
    False is the state the 're-cutting clears Parts' warning (G) gates on."""
    mesh, texture, centers = _pick_mesh()
    vm = PartsViewModel()
    vm.rebind(mesh, texture)
    vm.createPart()
    _click(vm, centers[0])  # carve some faces into a Part
    assert vm.hasParts is True

    new_mesh, new_texture, _ = _pick_mesh()  # a new cut settles
    vm.rebind(new_mesh, new_texture)

    assert vm.hasParts is False  # Parts cleared
    assert [r["name"] for r in vm.partsRows] == ["Unassigned"]
    assert vm.activePartId == 0  # edit target back to the remainder


class _FakeSimplifier:
    """Returns the model unchanged per cut — the Parts wiring only needs its mesh."""

    def __init__(self, model):
        self.model = model

    def simplify(self, target_faces, preserve=None):
        return self.model

    def close(self):
        pass


def _geom_source_model(path, mesh):
    return SourceModel(
        source_path=Path(path), geometry=mesh, face_count=int(mesh.faces.shape[0]),
        object_count=1, texture_path=None,
        objects=(SceneObject(name=Path(path).stem, face_count=int(mesh.faces.shape[0])),),
    )


def _load(proc, path="couch.obj", timeout=5.0):
    deadline = time.time() + timeout
    proc.loadFile(path)
    while (proc._simplified is None or proc.busy) and time.time() < deadline:
        time.sleep(0.005)


def test_processor_exposes_the_parts_view_model_and_rebinds_it_on_each_cut(monkeypatch):
    """The Processor owns a PartsViewModel exposed as `parts`, and rebinds it to the
    simplified mesh whenever a cut settles — so the Parts panel always carves the
    exact geometry the exporter writes, and a re-cut clears stale Parts."""
    mesh, _, _ = _pick_mesh()
    model = _geom_source_model("couch.obj", mesh)
    monkeypatch.setattr(processor_module, "load_source_model", lambda p: model)
    monkeypatch.setattr(processor_module, "ModelSimplifier", lambda m: _FakeSimplifier(m))

    proc = Processor()
    assert isinstance(proc.parts, PartsViewModel)  # exposed to QML

    _load(proc)  # load + the default −75% cut settles

    assert proc.parts.totalFaceCount == mesh.faces.shape[0]  # bound to the simplified mesh
    assert proc.parts.hasParts is False  # a fresh partition, nothing carved
