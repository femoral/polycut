# 0001 — "Export to SketchUp" writes Collada (.dae), not native .skp

Polycut's primary export writes a `.dae` (Collada) file rather than a native `.skp`. Native `.skp` requires the SketchUp C++ SDK, which has no clean Python binding and would complicate the PyInstaller build; SketchUp Pro (the target user's edition) imports `.dae` natively with full material/UV fidelity, giving a visually equivalent result. The user currently receives `.skp` from Transmutr and has accepted `.dae` as equivalent for now.

Native `.skp` export via the SDK is a deferred future enhancement, not v1.
