"""The bridge exposes the current mesh + texture to the Qt3D viewport (#8).

Acceptance #4: mesh/texture data is present on a testable view-model after a
load, without instantiating the 3D scene. These drive the bridge with fake
geometry (a real tiny trimesh, no PyMeshLab) so they stay fast and assert the
data the QML ``QQuick3DGeometry`` consumes — the render itself is HITL (#15).
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import trimesh

from polycut.bridge import processor as processor_module
from polycut.bridge.processor import Processor
from polycut.core import build_mesh_buffers
from polycut.core.model import SourceModel


def _quad_model(path, texture=None):
    """A real 2-triangle quad as a SourceModel — fast, exact, render-ready."""
    vertices = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=np.float64)
    faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    normals = np.tile([0.0, 0.0, 1.0], (4, 1))
    uv = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float64)
    mesh = trimesh.Trimesh(
        vertices=vertices,
        faces=faces,
        vertex_normals=normals,
        visual=trimesh.visual.TextureVisuals(uv=uv),
        process=False,
    )
    return SourceModel(
        source_path=Path(path),
        geometry=mesh,
        face_count=2,
        object_count=1,
        texture_path=Path(texture) if texture else None,
    )


def _triangle_model(path):
    """A coarser 1-triangle mesh — stands in for a more aggressive cut."""
    mesh = trimesh.Trimesh(
        vertices=np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float64),
        faces=np.array([[0, 1, 2]], dtype=np.int64),
        vertex_normals=np.tile([0.0, 0.0, 1.0], (3, 1)),
        process=False,
    )
    return SourceModel(
        source_path=Path(path),
        geometry=mesh,
        face_count=1,
        object_count=1,
        texture_path=None,
    )


class _FakeSimplifier:
    """Returns pre-canned real meshes per cut so the after-side has geometry to expose."""

    def __init__(self, model, results):
        self.model = model
        self._results = list(results)

    def simplify(self, target_faces, preserve=None):
        result = self._results[0] if len(self._results) == 1 else self._results.pop(0)
        return result

    def close(self):
        pass


def _wait_settled(proc, timeout=5.0):
    deadline = time.time() + timeout
    while (proc._simplified is None or proc.busy) and time.time() < deadline:
        time.sleep(0.005)


def test_mesh_data_exposes_loaded_geometry_and_texture(monkeypatch):
    """After a load, simplifiedMesh carries the rendered mesh's counts + its texture."""
    quad = _quad_model("a.obj", texture="baked.png")
    monkeypatch.setattr(processor_module, "load_source_model", lambda p: quad)
    monkeypatch.setattr(
        processor_module, "ModelSimplifier", lambda m: _FakeSimplifier(m, [quad])
    )

    proc = Processor()
    proc.loadFile("a.obj")
    _wait_settled(proc)

    mesh = proc.simplifiedMesh
    assert mesh.hasMesh is True
    assert mesh.triangleCount == 2
    assert mesh.vertexCount == 4
    assert mesh.textureUrl.fileName() == "baked.png"


def test_mesh_data_tracks_the_latest_cut(monkeypatch):
    """simplifiedMesh reflects the current cut, not the original or a stale one."""
    quad = _quad_model("a.obj")
    triangle = _triangle_model("a.obj")
    monkeypatch.setattr(processor_module, "load_source_model", lambda p: quad)
    monkeypatch.setattr(
        processor_module,
        "ModelSimplifier",
        lambda m: _FakeSimplifier(m, [quad, triangle]),
    )

    proc = Processor()
    proc.loadFile("a.obj")  # default reduction → quad (2 triangles)
    _wait_settled(proc)
    assert proc.simplifiedMesh.triangleCount == 2

    proc.simplify(1)  # a more aggressive cut → triangle (1 triangle)
    deadline = time.time() + 5.0
    while proc.busy and time.time() < deadline:
        time.sleep(0.005)

    assert proc.simplifiedMesh.triangleCount == 1
    assert proc.simplifiedMesh.vertexCount == 3


def test_mesh_data_exposes_raw_buffers_for_the_geometry(monkeypatch):
    """The geometry consumes the same bytes/stride/bounds the core builder emits."""
    quad = _quad_model("a.obj")
    monkeypatch.setattr(processor_module, "load_source_model", lambda p: quad)
    monkeypatch.setattr(
        processor_module, "ModelSimplifier", lambda m: _FakeSimplifier(m, [quad])
    )

    proc = Processor()
    proc.loadFile("a.obj")
    _wait_settled(proc)

    mesh = proc.simplifiedMesh
    expected = build_mesh_buffers(quad)
    assert bytes(mesh.vertexData()) == expected.vertex_data
    assert bytes(mesh.indexData()) == expected.index_data
    assert mesh.stride == expected.stride
    assert (mesh.boundsMin.x(), mesh.boundsMin.y(), mesh.boundsMin.z()) == expected.bounds_min
    assert (mesh.boundsMax.x(), mesh.boundsMax.y(), mesh.boundsMax.z()) == expected.bounds_max
