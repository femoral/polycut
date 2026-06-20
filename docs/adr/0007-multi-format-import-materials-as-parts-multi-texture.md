# 0007 — Imported models: materials become initial Parts, multi-texture throughout, per-submesh simplify (extends 0004)

> Status: accepted — extends/revises ADR-0004.

ADR-0004 assumed the Source is a single baked-material Meshy **soup**, carved Parts by colour on the simplified mesh, and **deferred per-part decimation** because the soup has no clean seams. MVP-4 broadens import to **GLB/glTF, DAE, OBJ** (textured) and geometry-only **PLY/STL/OFF**, so Polycut serves models from many tools, not only Meshy.

An imported model's **existing materials/meshes seed the initial Partition** — each material becomes a Part — rather than flattening to one Unassigned blob. To keep that coherent (otherwise the face grouping survives but the visuals are lost and the GLB round-trip is pointless), textures are **multi-texture end-to-end**:

- **load** reads N textures and builds the initial Partition from the source material assignment;
- the **Auto-cluster** colour signal is sampled per-face from *its own* material's texture, falling back to **per-vertex colour**, then to **none** (geometry-only → manual carving only);
- **every exporter** (DAE, GLB, OBJ, SKP) emits per-Part materials each referencing their own image — replacing the single shared `<library_images>` / `SHARED_IMAGE_ID`.

**Simplify runs per-submesh** — each imported Part decimated independently — so labels survive the core op. This is tractable precisely because imported materials are *already separate pieces*, which is the seam problem that blocked per-part decimation on the soup in ADR-0004.

## Considered and rejected

- **Flatten every import to one Unassigned blob and re-carve.** Simplest, one pipeline — but discards the structure that made respecting the import worthwhile, and makes the round-trip pointless.
- **Single-baked-texture imports only.** Turns away most real GLB/DAE files; contradicts the multi-tool goal.
- **Whole-mesh simplify, then project Parts by nearest face.** Cheaper, but fuzzy at boundaries (ADR-0004's own objection to nearest-face). Per-submesh decimation is exact.

## Consequences

- The single-shared-texture assumption is replaced by **per-Part textures** across load, segment, and all four exporters — the largest single change in MVP-4.
- ADR-0004's per-part-decimation deferral is **lifted for imported (already-separate) Parts**; the Meshy single-material path keeps whole-mesh simplify + carve-after.
- Per-submesh simplify currently applies the global simplify settings to each submesh; per-Part **budgets** as a UI control remain a future add.
- Geometry-only imports (no colour signal) support only manual carving (the spatial brush); the Auto-cluster is disabled for them.
