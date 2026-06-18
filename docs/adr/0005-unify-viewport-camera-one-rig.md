# 0005 — Unify the viewport on one camera rig; drop OrbitCameraController

The viewport originally ran **two independent camera rigs**: a main `pivot`+`camera`
driven by QtQuick3D's `OrbitCameraController` (left-drag orbits) for the
shaded/edges/wireframe before-after split, and a separate `partsPivot`+`partsCamera`
driven by a custom MouseArea (left **paints**, right orbits, middle pans, wheel
zooms) for the parts render mode. The split existed so painting could own the left
button without fighting the camera, and so switching modes couldn't corrupt the
shaded view — but it meant the **viewpoint reset every time you crossed between
parts and the other modes**, which read as inconsistent (US: "camera shared across
all tabs"), and it left two control schemes for the same act of orbiting.

We **collapse to one rig**: a single `pivot`+`camera` that every render mode shares,
so the viewpoint persists across all mode switches and re-frames only on new-model
load and up-axis change. `OrbitCameraController` is **removed**; the parts-style
custom handler becomes the **single input handler**, active in all modes —
**right-orbit, middle-pan, wheel-zoom everywhere**, with **left reserved for the
paint tool** (live only in parts mode, inert elsewhere). The before/after
`afterCamera` continues to mirror `camera`'s scene transform, so the split stays in
lockstep for free.

## Consequences

- One uniform control scheme. The left button no longer orbits in any mode — a
  deliberate reversal of the old `OrbitCameraController` default — so orbiting is
  always right-drag. Left stays free for tools (paint today, selection later).
- Explode (ADR-area #3) and the cross-view Highlight both render against this one
  shared viewpoint, so they look consistent regardless of the active render mode.
- The isolation the two-rig design bought is replaced by **input gating**: the
  paint path binds the left button only in parts mode, so tools and navigation
  still never share a button — the original constraint is preserved without a
  second camera.

## Considered and rejected

- **Keep two rigs, sync position/rotation/zoom on every render-mode switch.** No
  removal of `OrbitCameraController`, smaller diff — but two sources of truth that
  drift, and the left-orbit / right-orbit control mismatch between modes survives.
  Rejected: a single rig is less state and has no sync-drift failure mode.
