"""Part data model — the partition of a simplified mesh into reassignable Parts.

The MVP-3 foundation slice (#20): a per-face label array + a Part table, with the
**partition invariant** enforced in ``core`` — every face carries exactly one
label, the built-in **Unassigned** Part (id 0) holds whatever hasn't been carved,
and no op leaves a gap or an overlap. Pure headless ``core``, no Qt. These tests
pin the invariant and each face-moving op at the public seam.
"""

from __future__ import annotations

import numpy as np
import pytest

from polycut.core.parts import UNASSIGNED_ID, Partition


def test_fresh_partition_is_all_unassigned():
    """A fresh partition is one Unassigned Part owning 100% of the faces."""
    partition = Partition.fresh(face_count=10)

    assert [p.id for p in partition.parts] == [UNASSIGNED_ID]
    assert partition.face_count(UNASSIGNED_ID) == 10


def test_unassigned_cannot_be_deleted():
    """Unassigned is the partition's remainder — deleting it would break exhaustiveness,
    so the op is refused."""
    partition = Partition.fresh(face_count=10)

    with pytest.raises(ValueError):
        partition.delete(UNASSIGNED_ID)


def test_rename_changes_a_parts_name_without_touching_its_faces():
    """Renaming relabels the Part (so the SketchUp group reads 'frame', not 'Part 1')
    and leaves the face ownership alone."""
    partition = Partition.fresh(face_count=10)
    part = partition.create_part(name="Part 1")
    partition.assign([2, 5, 7], part)

    partition.rename(part, "frame")

    assert partition.part(part).name == "frame"
    assert partition.face_count(part) == 3


def test_assign_steals_faces_from_their_previous_owner():
    """Assigning a face set to a Part removes exactly those faces from Unassigned;
    the partition stays exhaustive (the two counts still sum to the mesh)."""
    partition = Partition.fresh(face_count=10)

    frame = partition.create_part(name="frame")
    partition.assign([2, 5, 7], frame)

    assert partition.face_count(frame) == 3
    assert partition.face_count(UNASSIGNED_ID) == 7


def test_delete_returns_a_parts_faces_to_unassigned():
    """Deleting a Part drops it from the table and hands its faces back to
    Unassigned — the partition stays whole, nothing is orphaned."""
    partition = Partition.fresh(face_count=10)
    frame = partition.create_part(name="frame")
    partition.assign([2, 5, 7], frame)

    partition.delete(frame)

    assert [p.id for p in partition.parts] == [UNASSIGNED_ID]
    assert partition.face_count(UNASSIGNED_ID) == 10


def test_merge_unions_two_parts_and_drops_the_emptied_one():
    """Merging folds one Part's faces into another and drops the now-empty Part —
    the fix for an over-split (lit + shadowed wood landing in separate Parts)."""
    partition = Partition.fresh(face_count=10)
    lit = partition.create_part(name="lit wood")
    shadow = partition.create_part(name="shadowed wood")
    partition.assign([0, 1], lit)
    partition.assign([2, 3], shadow)

    partition.merge(lit, shadow)

    assert [p.id for p in partition.parts] == [UNASSIGNED_ID, lit]
    assert partition.face_count(lit) == 4


def test_assign_steals_faces_from_another_part_not_only_unassigned():
    """Re-assigning faces that already belong to a Part moves them out of that Part —
    selection tools add to the active Part by stealing from whoever owned the face."""
    partition = Partition.fresh(face_count=10)
    legs = partition.create_part(name="legs")
    frame = partition.create_part(name="frame")
    partition.assign([4, 5, 6], legs)

    partition.assign([5, 6], frame)  # steal two faces away from legs

    assert partition.face_count(legs) == 1
    assert partition.face_count(frame) == 2
    assert partition.face_count(UNASSIGNED_ID) == 7


def test_new_parts_get_distinct_default_colours():
    """Each new Part is born with its own colour so the swatch and flat-colour Parts
    view can tell them apart without the designer picking colours by hand."""
    partition = Partition.fresh(face_count=10)

    wood = partition.create_part(name="wood")
    fabric = partition.create_part(name="fabric")

    assert partition.part(wood).colour != partition.part(fabric).colour


def test_a_part_can_be_hidden():
    """A Part starts visible and can be hidden, so the designer can see behind it
    while carving another — the hide toggle leaves face ownership alone."""
    partition = Partition.fresh(face_count=10)
    cushions = partition.create_part(name="cushions")
    partition.assign([0, 1, 2], cushions)

    assert partition.part(cushions).visible is True

    partition.set_visible(cushions, False)

    assert partition.part(cushions).visible is False
    assert partition.face_count(cushions) == 3


def test_each_part_has_a_distinct_material_slot_stable_across_rename():
    """Every Part carries its own material slot (what becomes a swappable SketchUp
    material). Slots are distinct per Part and stable across a rename, so two Parts
    sharing a display name still export as separate slots."""
    partition = Partition.fresh(face_count=10)
    a = partition.create_part(name="wood")
    b = partition.create_part(name="wood")  # same display name on purpose

    slot_before = partition.part(a).material_slot
    assert slot_before != partition.part(b).material_slot

    partition.rename(a, "frame")

    assert partition.part(a).material_slot == slot_before  # rename leaves the slot


def test_partition_round_trips_through_serialisation_unchanged():
    """The partition serialises to a plain dict and back unchanged — labels and the
    full Part table (name, colour, slot, visibility) survive, ready for a
    crash-recovery temp file or a project file later."""
    partition = Partition.fresh(face_count=10)
    frame = partition.create_part(name="frame")
    cushions = partition.create_part(name="cushions")
    partition.assign([0, 1, 2], frame)
    partition.assign([3, 4], cushions)
    partition.set_visible(cushions, False)

    restored = Partition.from_dict(partition.to_dict())

    assert np.array_equal(restored.labels, partition.labels)
    assert restored.parts == partition.parts


def _assert_partition_invariant(partition, face_count):
    """Every face carries exactly one label that names a current Part, so the
    per-Part counts sum to the mesh and no label is orphaned."""
    counts = [partition.face_count(p.id) for p in partition.parts]
    assert sum(counts) == face_count  # exhaustive + non-overlapping
    part_ids = {p.id for p in partition.parts}
    assert set(np.unique(partition.labels)).issubset(part_ids)  # no orphan labels


def test_invariant_survives_a_sequence_of_ops():
    """After create / assign / delete / merge in sequence the partition stays whole —
    on a heavy (646k-scale) face count, the model is mesh-agnostic so a plain count
    stands in for real geometry."""
    face_count = 646_000
    partition = Partition.fresh(face_count=face_count)
    _assert_partition_invariant(partition, face_count)

    wood = partition.create_part(name="wood")
    fabric = partition.create_part(name="fabric")
    legs = partition.create_part(name="legs")
    partition.assign(np.arange(0, 300_000), wood)
    partition.assign(np.arange(300_000, 500_000), fabric)
    partition.assign(np.arange(250_000, 320_000), legs)  # deliberately overlaps wood + fabric
    _assert_partition_invariant(partition, face_count)

    partition.delete(fabric)  # faces back to Unassigned
    _assert_partition_invariant(partition, face_count)

    partition.merge(wood, legs)  # fold legs into wood
    _assert_partition_invariant(partition, face_count)


def test_labels_are_read_only():
    """``labels`` is exposed read-only so callers (the bridge, the export, a view)
    can read the partition but only the ops can mutate it — the invariant can't be
    broken behind the model's back."""
    partition = Partition.fresh(face_count=10)

    with pytest.raises(ValueError):
        partition.labels[0] = 5


def test_merge_cannot_drop_unassigned():
    """Merging away Unassigned would break exhaustiveness just as deleting it would,
    so folding *from* Unassigned is refused."""
    partition = Partition.fresh(face_count=10)
    frame = partition.create_part(name="frame")

    with pytest.raises(ValueError):
        partition.merge(frame, UNASSIGNED_ID)  # would drop Unassigned
