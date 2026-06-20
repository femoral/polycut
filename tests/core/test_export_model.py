"""The export_model orchestrator — the whole transform→parts→export pipeline (#33).

The "Export to SketchUp" pipeline (apply the Transform, attach the carved Parts,
write the Collada file) lived only as inline steps inside the Qt export worker, so
its *composition* was reachable only through Qt. ``export_model`` is that pipeline
as one headless entry point above the (unchanged) ``export_collada`` writer. These
pin it end-to-end with no Qt: the written document equals the manual chain's, a
stale partition degrades to a single group, and the declared unit follows the
Transform's target unit.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh
from collada import Collada
from PIL import Image

from polycut.core import (
    Partition,
    Transform,
    export_collada,
    export_model,
    remap_up_axis,
    scale_geometry,
)
from polycut.core.model import SourceModel


def _box_model(extents=(1.0, 2.0, 3.0)):
    box = trimesh.creation.box(extents=extents)
    return SourceModel(
        source_path=Path("box.obj"),
        geometry=box,
        face_count=int(box.faces.shape[0]),
        object_count=1,
        textures=(),
    )


def _extents(path: Path):
    mesh = trimesh.load(str(path), force="mesh")
    return mesh.bounds[1] - mesh.bounds[0]


def test_output_equals_the_manual_transform_then_export_chain(tmp_path):
    """The orchestrator writes the same baked geometry as the inline
    scale→orient→export_collada chain the worker ran by hand."""
    model = _box_model()
    transform = Transform(multiplier=2.0, source_unit="m", target_unit="m", up_axis="z")

    out = tmp_path / "orchestrated.dae"
    export_model(model, out, transform)

    manual_model = remap_up_axis(scale_geometry(model, 2.0), "z")
    manual = tmp_path / "manual.dae"
    export_collada(manual_model, manual, unit_name="meter", unit_meters=1.0)

    assert np.allclose(_extents(out), _extents(manual))


def _faces_model(n_faces=4):
    """A mesh of ``n_faces`` independent triangles — Parts carve cleanly per face."""
    verts, faces = [], []
    for i in range(n_faces):
        base = 3 * i
        verts += [[i, 0, 0], [i + 1, 0, 0], [i, 1, 0]]
        faces.append([base, base + 1, base + 2])
    mesh = trimesh.Trimesh(
        vertices=np.array(verts, float), faces=np.array(faces, np.int64), process=False
    )
    return SourceModel(Path("m.obj"), mesh, n_faces, 1, ())


def test_a_stale_partition_degrades_to_one_group(tmp_path):
    """A partition whose label count no longer matches the mesh (a carve from a prior
    cut) is dropped — the model still exports as a single valid group, never split on
    indices that no longer line up."""
    model = _faces_model(n_faces=4)
    transform = Transform(1.0, "m", "m", "y")

    # A partition carved over a *different* (6-face) mesh — two parts that would
    # otherwise write two groups, but the labels no longer match the 4-face model.
    stale = Partition.fresh(6)
    frame = stale.create_part(name="frame")
    cushions = stale.create_part(name="cushions")
    stale.assign([0, 1, 2], frame)
    stale.assign([3, 4, 5], cushions)

    out = tmp_path / "stale.dae"
    export_model(model, out, transform, partition=stale)

    doc = Collada(str(out))
    assert len(doc.geometries) == 1  # degraded to a single group, not the stale carve


def test_declared_unit_follows_the_transforms_target_unit(tmp_path):
    """The Collada ``<unit>`` metadata declares the Transform's target unit, so
    SketchUp imports at the right size."""
    model = _box_model()
    transform = Transform(1.0, "m", "cm", "y")

    out = tmp_path / "unit.dae"
    export_model(model, out, transform)

    doc = Collada(str(out))
    assert doc.assetInfo.unitname == "centimeter"
    assert doc.assetInfo.unitmeter == 0.01


def test_a_matching_partition_writes_the_carved_named_groups(tmp_path):
    """A partition whose labels match the mesh carries through — each non-empty Part
    becomes its own named group, exactly as the manual chain produced."""
    model = _faces_model(n_faces=4)
    transform = Transform(1.0, "m", "m", "y")

    partition = Partition.fresh(4)
    frame = partition.create_part(name="frame")
    cushions = partition.create_part(name="cushions")
    partition.assign([0, 1], frame)
    partition.assign([2, 3], cushions)

    out = tmp_path / "carved.dae"
    export_model(model, out, transform, partition=partition)

    doc = Collada(str(out))
    assert {m.name for m in doc.materials} == {"frame", "cushions"}
