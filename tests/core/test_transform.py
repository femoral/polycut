"""The Transform value object — the scale + units + up-axis bundle (#33).

ADR-0004 names ``simplify → transform → parts → export`` but the transform stage
had no headless home: the scale→orient compose, the factor-of-one skip, and the
size readout lived only inside the Qt export worker. Transform formalises that
stage as a frozen value, composing the existing ``scale_geometry`` and
``remap_up_axis`` helpers. These pin its behaviour through the public interface —
that applying it equals the manual chain, that it reports the baked dimensions and
unit metadata — never the private composition.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh

from polycut.core import remap_up_axis, scale_geometry
from polycut.core.model import SourceModel
from polycut.core.transform import Transform


def _box_model(extents=(1.0, 2.0, 3.0)):
    """A box with distinct per-axis extents — scale and rotation are both observable."""
    box = trimesh.creation.box(extents=extents)
    return SourceModel(
        source_path=Path("box.obj"),
        geometry=box,
        face_count=int(box.faces.shape[0]),
        object_count=1,
        texture_path=None,
    )


def test_apply_equals_the_manual_scale_then_orient_chain():
    """Applying a Transform produces the same geometry as the existing
    scale-then-orient chain the export worker ran inline."""
    model = _box_model()
    transform = Transform(multiplier=2.0, source_unit="m", target_unit="m", up_axis="z")

    applied = transform.apply(model)

    manual = remap_up_axis(scale_geometry(model, 2.0), "z")
    assert np.allclose(applied.geometry.vertices, manual.geometry.vertices)


def test_a_unit_factor_of_one_skips_the_scale_copy():
    """A factor of exactly one (multiplier 1, matching units) skips the scale step,
    so a y-up no-op Transform returns the very same model — no copy of the (heavy)
    geometry just to multiply by one."""
    model = _box_model()
    transform = Transform(multiplier=1.0, source_unit="m", target_unit="m", up_axis="y")

    assert transform.apply(model) is model


def test_dimensions_equal_the_factor_times_the_raw_extents():
    """The reported real-world dimensions are the raw bounding-box extents times the
    linear factor — the cheap readout, no mesh copy or rotation."""
    model = _box_model((1.0, 2.0, 3.0))
    transform = Transform(multiplier=1.0, source_unit="m", target_unit="cm", up_axis="y")

    # m→cm is ×100
    assert np.allclose(transform.dimensions(model), (100.0, 200.0, 300.0))


def test_dimensions_are_magnitude_stable_across_up_axis():
    """Up-axis only permutes which extent maps to which axis — it never changes the
    set of magnitudes, so the readout needs no rotation and stays stable."""
    model = _box_model((1.0, 2.0, 3.0))
    base = Transform(1.0, "m", "m", "y").dimensions(model)

    for axis in ("x", "y", "z"):
        rotated = Transform(1.0, "m", "m", axis).dimensions(model)
        assert sorted(rotated) == sorted(base)


def test_unit_metadata_matches_the_target_unit():
    """The Collada ``<unit>`` metadata (full name + metres) follows the target unit,
    not the source — that is the unit the geometry is baked to."""
    transform = Transform(multiplier=1.0, source_unit="mm", target_unit="cm", up_axis="y")

    assert transform.unit_name == "centimeter"
    assert transform.unit_meters == 0.01
