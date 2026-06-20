# 0001 — "Export to SketchUp" writes Collada (.dae), not native .skp

> Status: superseded by ADR-0006 — SketchUp Free (Web) can't import `.dae`, so native `.skp` became the SketchUp export and `.dae` was demoted to generic interop.

Polycut's primary export writes a `.dae` (Collada) file rather than a native `.skp`. Native `.skp` requires the SketchUp C++ SDK, which has no clean Python binding and would complicate the PyInstaller build; SketchUp Pro (the target user's edition) imports `.dae` natively with full material/UV fidelity, giving a visually equivalent result. The user currently receives `.skp` from Transmutr and has accepted `.dae` as equivalent for now.

Native `.skp` export via the SDK is a deferred future enhancement, not v1.
