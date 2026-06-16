"""Scale + units — sizing a Source model to its real-world dimensions.

Meshy exports at an arbitrary scale, so the user picks a multiplier plus source
and target units to land the model at the right size in SketchUp (the step that
used to need Transmutr). The scale is **baked into the geometry** and the chosen
target unit is also declared in the Collada ``<unit>`` metadata, so SketchUp Pro
imports at the correct size without relying on its import-units dialog.

Meshy exports carry no unit metadata, so :func:`detect_source_unit` infers one
from the model's size to pre-fill the source unit (overridable). Up-axis
orientation is a separate concern — see :mod:`polycut.core.orient`.
"""

from __future__ import annotations

from polycut.core.model import SourceModel

# How many metres one unit of each supported unit represents.
UNIT_METERS = {
    "mm": 0.001,
    "cm": 0.01,
    "m": 1.0,
    "in": 0.0254,
    "ft": 0.3048,
}

# Full names for the Collada ``<unit>`` declaration.
UNIT_NAMES = {
    "mm": "millimeter",
    "cm": "centimeter",
    "m": "meter",
    "in": "inch",
    "ft": "foot",
}


def scale_factor(multiplier: float, source_unit: str, target_unit: str) -> float:
    """The single linear factor that re-expresses ``source_unit`` coordinate
    values in ``target_unit``, times a free ``multiplier``.

    Baked into the geometry alongside a ``target_unit`` ``<unit>`` declaration,
    this makes the real-world size ``raw × multiplier × metres(source_unit)``.
    """
    return multiplier * UNIT_METERS[source_unit] / UNIT_METERS[target_unit]


# A real-world product (couch, chair, table) is plausibly between 0.1 m and 10 m
# across. Detection picks the unit whose numbers land the model in that band.
_FURNITURE_MIN_M = 0.1
_FURNITURE_MAX_M = 10.0


def detect_source_unit(model: SourceModel) -> str:
    """Infer the unit the model's coordinates are expressed in, from its size.

    Meshy exports real-world-scaled geometry but declares no unit, so we read the
    largest bounding-box extent and pick the unit that lands the model in a
    furniture-plausible range (~0.1–10 m). Units are tried metres-first so an
    ambiguous size resolves to ``"m"`` — Meshy's native scale. Falls back to
    ``"m"`` when nothing fits (the safe default for a Meshy source).
    """
    lo, hi = model.geometry.bounds
    largest = float(max(hi - lo))
    for unit in ("m", "cm", "mm", "in", "ft"):
        if _FURNITURE_MIN_M <= largest * UNIT_METERS[unit] <= _FURNITURE_MAX_M:
            return unit
    return "m"


def scale_geometry(model: SourceModel, factor: float) -> SourceModel:
    """Return a new :class:`SourceModel` whose geometry is scaled by ``factor``.

    Topology, UVs and the texture are untouched — only vertex positions move, so
    the face count and texture carry over unchanged.
    """
    geometry = model.geometry.copy()
    # A uniform positive scale leaves unit normals unchanged, but trimesh drops
    # the cached normals on any transform — carry them across so the export
    # doesn't (slowly) recompute them for a heavy mesh.
    normals = getattr(geometry, "vertex_normals", None)
    geometry.apply_scale(factor)
    if normals is not None:
        geometry.vertex_normals = normals

    return SourceModel(
        source_path=model.source_path,
        geometry=geometry,
        face_count=model.face_count,
        object_count=model.object_count,
        texture_path=model.texture_path,
    )
