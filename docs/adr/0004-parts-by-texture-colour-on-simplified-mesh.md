# 0004 — Parts: carve by per-face texture colour on the simplified mesh; topology/material can't

A Meshy Source model is a single baked-material **topological soup** — the 646k
sofa fixture is 2,529 disconnected shards, none larger than ~0.6% of faces — so a
Part boundary (frame vs cushion) lives in the *designer's head*, not in the
geometry, and can't fall out of connectivity or material. The one signal that
tracks that boundary is **per-face baked-texture colour**: sampling each face's
UVs into the texture cleanly separates the brown wood from the grey fabric
(k-means on the fixture splits wood/fabric at k=2). MVP-3 therefore carves Parts
by colour, with manual escape hatches (a colour wand and a spatial brush) for
seams colour can't see (legs vs frame, same wood).

Parts are carved on the **simplified** mesh — pipeline order
`simplify → transform → parts → export`. Labels then live on the final faces, so
the partition is exact and the Parts preview equals the export with zero
label-mapping (honouring ADR-0003's faithfulness guarantee). The segmentation
logic is kept **mesh-agnostic** (`segment(mesh, texture) → per-face labels`) and a
Part is stored as a relabelable, serialisable per-face label array plus a Part
table (name, material slot, colour), so cut-first ordering, per-part decimation,
and a crash-recovery/project file can be added later without a data-model rewrite.

## Considered and rejected

- **Topology / connected-components split.** The soup yields 2,529 meaningless
  shards, not pieces. Flood-fill by connectivity is dead for the same reason.
- **Material-slot split.** Meshy bakes exactly one material; nothing to separate.
- **Cut-first (carve the 646k original, then simplify).** Gives finer seam
  resolution and opens per-part decimation (wood wants planar/hard-edge
  constraints, cushions want a smooth organic budget). But a *whole-mesh* collapse
  merges faces across Part seams and destroys labels; keeping labels exact needs
  per-part submesh decimation with seam/crack handling on a non-manifold soup.
  Deferred, not blocked — the mesh-agnostic core leaves the door open.
- **Re-cut re-projecting Parts by nearest-face.** Fuzzy at exactly the seams that
  matter. Instead, re-simplifying after Parts exist **clears** them, with a warning.

## Consequences

- Re-simplifying after Parts exist clears the partition (warned up front).
- De-shine stays a non-goal: the split + per-Part material slots *is* the material
  fix — the designer reassigns materials per-piece in SketchUp, no face-by-face
  painting.
