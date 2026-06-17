"""The Part data model — a partition of the simplified mesh into Parts.

A **Part** is a named, non-overlapping subset of the mesh's faces carrying its own
material slot. The model stores a per-face ``int32`` **label array** plus a **Part
table** (id, name, material slot, colour, visibility). The built-in **Unassigned**
Part (id 0) holds every face not yet carved into another Part.

The **partition invariant** is enforced here, never by callers: every face carries
exactly one label, so ``sum(per-Part face counts) == mesh face count`` always — no
gaps, no overlaps. All ops move faces *between* Parts; Unassigned is permanent.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

UNASSIGNED_ID = 0

UNASSIGNED_COLOUR = (130, 130, 130)  # neutral grey — the not-yet-carved remainder

# A categorical palette so freshly-carved Parts read as distinct in the flat-colour
# Parts view and the outliner swatch, without the designer choosing colours by hand.
_PART_COLOURS = (
    (228, 94, 80),    # red
    (76, 154, 224),   # blue
    (108, 191, 110),  # green
    (240, 173, 78),   # amber
    (158, 118, 200),  # purple
    (88, 197, 196),   # teal
    (224, 122, 180),  # pink
    (170, 152, 110),  # tan
)


@dataclass(frozen=True)
class Part:
    """One row of the Part table."""

    id: int
    name: str
    colour: tuple[int, int, int]
    material_slot: str
    visible: bool = True


class Partition:
    """A per-face label array over a mesh, plus its Part table."""

    def __init__(self, labels: np.ndarray, parts: dict[int, Part]) -> None:
        self._labels = labels
        self._parts = parts

    @classmethod
    def fresh(cls, face_count: int) -> Partition:
        """A fresh partition: every face owned by Unassigned."""
        labels = np.zeros(face_count, dtype=np.int32)
        unassigned = Part(
            id=UNASSIGNED_ID,
            name="Unassigned",
            colour=UNASSIGNED_COLOUR,
            material_slot="unassigned",
        )
        return cls(labels, {UNASSIGNED_ID: unassigned})

    @property
    def labels(self) -> np.ndarray:
        """The per-face label array, as a read-only view (ops are the only mutators)."""
        view = self._labels.view()
        view.flags.writeable = False
        return view

    @property
    def parts(self) -> tuple[Part, ...]:
        return tuple(self._parts.values())

    def part(self, part_id: int) -> Part:
        return self._parts[part_id]

    def face_count(self, part_id: int) -> int:
        return int(np.count_nonzero(self._labels == part_id))

    def create_part(self, name: str) -> int:
        """Add an empty Part to the table; return its stable id."""
        part_id = max(self._parts) + 1  # ids are never recycled
        colour = _PART_COLOURS[(part_id - 1) % len(_PART_COLOURS)]
        self._parts[part_id] = Part(
            id=part_id,
            name=name,
            colour=colour,
            material_slot=f"slot-{part_id}",  # stable + distinct; survives rename
        )
        return part_id

    def assign(self, face_ids, part_id: int) -> None:
        """Move ``face_ids`` to ``part_id``, stealing them from their current owners."""
        self._labels[np.asarray(face_ids, dtype=np.int64)] = part_id

    def delete(self, part_id: int) -> None:
        """Drop a Part, returning its faces to Unassigned."""
        self._relabel_and_drop(part_id, UNASSIGNED_ID)

    def merge(self, into_id: int, from_id: int) -> None:
        """Fold ``from_id``'s faces into ``into_id`` and drop the emptied Part."""
        self._relabel_and_drop(from_id, into_id)

    def _relabel_and_drop(self, from_id: int, into_id: int) -> None:
        """Relabel ``from_id``'s faces to ``into_id`` and drop ``from_id`` — the
        shared core of delete and merge. Refused for Unassigned, which is permanent
        (dropping it would break exhaustiveness)."""
        if from_id == UNASSIGNED_ID:
            raise ValueError("Unassigned is the partition remainder; it cannot be dropped")
        self._labels[self._labels == from_id] = into_id
        del self._parts[from_id]

    def rename(self, part_id: int, name: str) -> None:
        """Change a Part's name, leaving its face ownership untouched."""
        self._parts[part_id] = replace(self._parts[part_id], name=name)

    def set_visible(self, part_id: int, visible: bool) -> None:
        """Show or hide a Part, leaving its face ownership untouched."""
        self._parts[part_id] = replace(self._parts[part_id], visible=visible)

    def to_dict(self) -> dict:
        """A JSON-friendly snapshot — the label array plus the Part table."""
        return {
            "labels": self._labels.tolist(),
            "parts": [
                {
                    "id": p.id,
                    "name": p.name,
                    "colour": list(p.colour),
                    "material_slot": p.material_slot,
                    "visible": p.visible,
                }
                for p in self._parts.values()
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> Partition:
        """Rebuild a Partition from :meth:`to_dict` output."""
        labels = np.asarray(data["labels"], dtype=np.int32)
        parts = {
            row["id"]: Part(
                id=row["id"],
                name=row["name"],
                colour=tuple(row["colour"]),
                material_slot=row["material_slot"],
                visible=row["visible"],
            )
            for row in data["parts"]
        }
        return cls(labels, parts)
