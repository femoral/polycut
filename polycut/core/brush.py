"""The spatial brush — paint Parts by proximity, headless `core`.

Where the colour wand fails — two pieces baked the same shade (legs vs frame, same
wood) — the brush carves by *space* instead of colour. Given a surface hit point
(from :func:`~polycut.core.picking.pick_face`) and a radius, it selects every face
whose **centroid** falls inside that sphere: proximity, not topology, so it reaches
across the shard soup where adjacency flood-fill cannot.

A :class:`SpatialBrush` builds one ``cKDTree`` over the mesh's face centroids and
reuses it for the life of the mesh — a drag is just a sequence of range queries
against that tree, so painting stays cheap no matter how long the stroke.
"""

from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree

from polycut.core.parts import Partition
from polycut.core.picking import add_to_part, subtract_from_part


class SpatialBrush:
    """A reusable proximity selector over a mesh's face centroids."""

    def __init__(self, mesh) -> None:
        self._tree = cKDTree(np.asarray(mesh.triangles_center, dtype=np.float64))

    def faces_within(self, point, radius: float) -> np.ndarray:
        """Face ids whose centroid lies within ``radius`` of ``point`` (inclusive)."""
        idx = self._tree.query_ball_point(np.asarray(point, dtype=np.float64), radius)
        return np.array(sorted(idx), dtype=np.int64)

    def swept_faces(self, points, radius: float) -> np.ndarray:
        """The union of :meth:`faces_within` over a drag's sequence of hit points —
        every face the brush passes over between mouse-down and mouse-up."""
        hits = self._tree.query_ball_point(np.asarray(points, dtype=np.float64), radius)
        return np.array(sorted({f for stamp in hits for f in stamp}), dtype=np.int64)

    def paint(self, partition: Partition, points, radius: float, part_id: int) -> None:
        """Paint a drag into ``part_id`` — the swept faces are stolen from their
        current owners, so the partition stays exhaustive and non-overlapping."""
        add_to_part(partition, self.swept_faces(points, radius), part_id)

    def erase(self, partition: Partition, points, radius: float, part_id: int) -> None:
        """Erase a drag from ``part_id`` — only the swept faces that Part actually
        owns return to Unassigned; faces belonging to other Parts are left alone."""
        subtract_from_part(partition, self.swept_faces(points, radius), part_id)
