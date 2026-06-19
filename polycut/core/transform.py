"""Transform — the scale + units + up-axis bundle baked at export (#33).

ADR-0004 names ``simplify → transform → parts → export`` as the pipeline, but the
**transform** stage had no headless home: the scale→orient compose, the
"skip the copy when the factor is one" optimisation, and the real-world size
readout lived only inside the Qt export worker. :class:`Transform` is that stage as
a frozen value — the same bundle the UI's Transform panel groups (scale multiplier,
source/target units, up-axis). It composes the existing :func:`scale_geometry` and
:func:`remap_up_axis` helpers rather than absorbing them; the partition (the carve)
is a separate concern and is never part of a Transform.
"""

from __future__ import annotations

from dataclasses import dataclass

from polycut.core.model import SourceModel
from polycut.core.orient import remap_up_axis
from polycut.core.scale import UNIT_METERS, UNIT_NAMES, scale_factor, scale_geometry


@dataclass(frozen=True)
class Transform:
    """The scale + units + up-axis settings the designer bakes into the model.

    Spatial/unit settings only — the carve (a :class:`Partition`) stays separate.
    """

    multiplier: float
    source_unit: str
    target_unit: str
    up_axis: str

    def apply(self, model: SourceModel) -> SourceModel:
        """Return ``model`` scaled then oriented — the export worker's inline chain.

        The scale copy is skipped when the factor is exactly one (a unit no-op);
        ``remap_up_axis`` already no-ops for a ``"y"`` (already-upright) up-axis.
        """
        factor = self.factor
        if factor != 1.0:
            model = scale_geometry(model, factor)
        return remap_up_axis(model, self.up_axis)

    def dimensions(self, model: SourceModel) -> tuple[float, float, float]:
        """The model's resulting real-world size: the raw bounding-box extents times
        the linear factor, in geometry-axis order.

        Cheap by construction — no mesh copy. Up-axis is irrelevant here: a rotation
        only permutes which extent maps to which axis, never the magnitudes, so the
        readout agrees with the baked export without rotating anything.
        """
        lo, hi = model.geometry.bounds
        ext = (hi - lo) * self.factor
        return float(ext[0]), float(ext[1]), float(ext[2])

    @property
    def factor(self) -> float:
        """The single linear factor re-expressing source-unit values in the target
        unit, times the free multiplier — baked alongside the ``<unit>`` declaration."""
        return scale_factor(self.multiplier, self.source_unit, self.target_unit)

    @property
    def unit_name(self) -> str:
        """The full name of the target unit for the Collada ``<unit>`` declaration."""
        return UNIT_NAMES[self.target_unit]

    @property
    def unit_meters(self) -> float:
        """How many metres one target unit represents, for the ``<unit>`` declaration."""
        return UNIT_METERS[self.target_unit]
