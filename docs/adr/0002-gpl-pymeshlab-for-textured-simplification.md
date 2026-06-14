# 0002 — Project is GPL; use PyMeshLab for texture-preserving simplification

This supersedes the manifest's "use Open3D (MIT) instead of PyMeshLab" decision.

Polycut is released as free, open-source software under the GPL. Simplification uses **PyMeshLab** (GPLv3), whose quadric edge-collapse-with-texture filter preserves UV texture coordinates through heavy reduction — directly serving the "looks good in SketchUp" bar, since Source models are a single baked-texture blob that smears badly under MIT-only simplifiers (Open3D, fast-simplification).

The manifest chose Open3D (MIT) to keep a future closed/paid build possible. The owner has confirmed the tool stays free/open; any future monetization comes from adjacent paid *services*, not a closed core. That closed-source optionality is not worth the degraded textured-decimation quality it would cost.

**Consequence:** GPL is viral — a PyInstaller bundle that includes PyMeshLab must be distributed under GPL with source available. Acceptable, since the project is open-source by intent.
