"""Shared fixtures for the core seam.

The Meshy sofa is 646k faces; loading and exporting it is the slow part. These
session-scoped fixtures do each once and share the immutable results, so the
suite pays the cost a single time.
"""

from pathlib import Path

import numpy as np
import pytest
import trimesh

from polycut.core import export_collada, load_source_model, simplify_model
from polycut.core.model import SourceModel

DEFAULT_REDUCTION = 0.25  # keep ~25% of faces (the −75% default applied on load)

SOFA = Path(__file__).resolve().parents[1] / "fixtures" / "meshy_sofa" / "model.obj"


def _write_textured_obj(directory: Path, name: str, vertices, faces, uv) -> Path:
    """Write a tiny per-wedge-textured ``.obj`` (+ ``.mtl``) the texture filter accepts.

    The texture-preserving quadric collapse refuses a mesh with inconsistent
    texcoords, so every face must reference a ``vt`` and the material must declare
    a ``map_Kd``. The referenced image need not exist on disk — decimation works on
    geometry + wedge UVs, never the pixels — so these fixtures stay plain text (no
    committed binaries), generated once into a tmp dir.
    """
    obj_path = directory / f"{name}.obj"
    (directory / f"{name}.mtl").write_text(
        f"newmtl {name}\nKd 0.8 0.8 0.8\nmap_Kd {name}.png\n"
    )
    lines = [f"mtllib {name}.mtl", f"usemtl {name}"]
    lines += [f"v {x} {y} {z}" for x, y, z in vertices]
    lines += [f"vt {u} {v}" for u, v in uv]
    lines += ["f " + " ".join(f"{i + 1}/{i + 1}" for i in face) for face in faces]
    obj_path.write_text("\n".join(lines) + "\n")
    return obj_path


def _model_from_obj(obj_path: Path, geometry) -> SourceModel:
    return SourceModel(
        source_path=obj_path,
        geometry=geometry,
        face_count=int(geometry.faces.shape[0]),
        object_count=1,
        textures=(),
    )


@pytest.fixture(scope="session")
def open_plane_model(tmp_path_factory):
    """A small open-boundary grid plane (textured) — boundary preservation is
    observable on it: 8×8 quads → a 32-vertex rim that ``preserveboundary`` keeps
    or collapses. Fast and deterministic, unlike the 646k sofa."""
    n = 8
    xs = np.linspace(0.0, 1.0, n + 1)
    verts = [(x, 0.0, z) for z in xs for x in xs]  # y-flat plane in the xz-grid
    uv = [(x, z) for z in xs for x in xs]
    faces = []
    for j in range(n):
        for i in range(n):
            a, b = j * (n + 1) + i, j * (n + 1) + i + 1
            c, d = (j + 1) * (n + 1) + i + 1, (j + 1) * (n + 1) + i
            faces += [(a, b, c), (a, c, d)]
    directory = tmp_path_factory.mktemp("open_plane")
    obj_path = _write_textured_obj(directory, "plane", verts, faces, uv)
    geometry = trimesh.Trimesh(vertices=np.array(verts), faces=np.array(faces), process=False)
    return _model_from_obj(obj_path, geometry)


@pytest.fixture(scope="session")
def creased_cube_model(tmp_path_factory):
    """A subdivided cube (textured) — its hard 90° creases make ``preservenormal``
    and ``planarquadric`` (hard edges) measurably change the collapse, where a flat
    plane or smooth sphere wouldn't."""
    box = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    for _ in range(3):
        box = box.subdivide()
    verts = box.vertices
    uv = np.column_stack([verts[:, 0] + 0.5, verts[:, 2] + 0.5])
    directory = tmp_path_factory.mktemp("creased_cube")
    obj_path = _write_textured_obj(directory, "cube", verts, box.faces, uv)
    geometry = trimesh.Trimesh(vertices=verts, faces=box.faces, process=False)
    return _model_from_obj(obj_path, geometry)


@pytest.fixture(scope="session")
def sofa_model():
    return load_source_model(SOFA)


@pytest.fixture(scope="session")
def exported_sofa(sofa_model, tmp_path_factory):
    """Export the sofa once; return (output_path, ExportResult, source_model)."""
    out = tmp_path_factory.mktemp("export") / "sofa.dae"
    result = export_collada(sofa_model, out)
    return out, result, sofa_model


@pytest.fixture
def box_model():
    """A 1×1×1 unit cube — a fast, exact stand-in for geometry/scale tests."""
    box = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    return SourceModel(
        source_path=Path("box.obj"),
        geometry=box,
        face_count=int(box.faces.shape[0]),
        object_count=1,
        textures=(),
    )


@pytest.fixture(scope="session")
def simplified_sofa(sofa_model):
    """Simplify the sofa once at the default reduction; return (result, target)."""
    target = round(sofa_model.face_count * DEFAULT_REDUCTION)
    return simplify_model(sofa_model, target), target
