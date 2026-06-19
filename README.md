# Polycut

Polycut is a desktop tool that turns a high-poly Meshy Source model into a
SketchUp-ready file. It simplifies the model to a workable polygon count, carves
it into per-piece material slots, sizes and orients it correctly, and exports it
as Collada (`.dae`). See [`CONTEXT.md`](CONTEXT.md) for the domain language and
[`docs/`](docs) for the design system and architecture decision records.

## Motivation

My girlfriend needed a way to simplify the models she generated with Meshy and
bring them into SketchUp. The fused, single-material exports were too heavy to
work with and gave her nothing to grab onto. Polycut started as that simplifier,
then grew a Parts feature so she could split a model into separate pieces and
swap their materials in SketchUp without painting face-by-face.

## What it does

You open a Meshy `.obj` and its `.mtl` and baked texture resolve automatically.
From there the work flows through four stages: simplify, transform, parts, and
export.

Simplification reduces the polygon count with texture-preserving quadric
decimation. You drive it with a reduction slider or a target-face count, step
through presets with the LOD stepper, and choose what to preserve — UVs, normals,
boundaries, and hard edges. The baked texture survives the cut without smearing.

The transform stage sizes and orients the model. You set a scale multiplier,
source and target units, and an up-axis; all of it is baked into the geometry at
export, and the target unit is also declared in the Collada `<unit>` metadata.

Parts are the heart of the tool. A Meshy export arrives as a single fused mesh
under one baked material, so there is nothing to select piece by piece. Polycut
carves it into named, non-overlapping Parts, each of which exports as its own
SketchUp group with its own swappable material slot — so the designer reassigns
materials per piece in SketchUp instead of painting hundreds of faces. Three
tools do the carving: an automatic colour cluster that groups faces by texture
colour with k-means in CIELAB, a colour wand that grows a selection by colour
either locally or across gaps in the geometry, and a spatial brush that paints
faces by proximity. A built-in Unassigned Part always holds whatever has not been
carved yet, so the export covers the whole model with no orphaned triangles. You
can rename, hide, merge, add, and delete Parts from the outliner.

Export writes a single textured `.dae` with one named node per Part, each
carrying its own material slot, all sharing the one baked texture, which is copied
beside the file. The model looks identical on import and arrives with as many
swappable slots as there are Parts.

Throughout, a live 3D viewport shows the work. It offers four render modes —
shaded, edges, wireframe, and a flat-colour parts view — and three view framings:
the full-resolution original, a draggable before/after split, and the simplified
cut on its own. A single shared camera rig keeps the viewpoint steady as you
switch between them. The active Part is drawn with a teal contour outline in every
render mode, and holding Space momentarily explodes the Parts apart so you can see
between them, with the wheel setting how far they spread. A processing chip
reports whenever a load, simplify, export, or cluster is running, and you can open
another model without restarting the app.

## Architecture

The code is split across three layers. The `polycut/core/` package is the
headless pipeline — loading, simplifying, transforming (scale and orient),
segmenting into Parts (cluster, wand, brush, and picking), building the viewport
buffers, and writing the multi-Part Collada export. It has no Qt dependency and is
the seam the tests exercise. The `polycut/bridge/` package holds the `processor`
QObject that exposes `core` to QML, along with the Parts view-model and the
buffer-source seam that feeds geometry to the viewport. The `polycut/ui/Polycut/`
package is the QML shell, the `Theme` singleton that is the single source of truth
for the design system, and the bundled Inter and JetBrains Mono fonts.

## Develop

Create a virtual environment, install the project in editable mode with the GUI
and dev extras, then run the app or the tests:

```sh
python -m venv .venv
.venv/bin/python -m ensurepip
.venv/bin/python -m pip install -e ".[gui,dev]"

.venv/bin/python -m polycut.app      # run the app
.venv/bin/python -m pytest           # run the tests (-m "not slow" to skip the big fixture)
```

On NixOS, the native libraries that the PySide6 / Qt and pymeshlab wheels dlopen
at runtime are not in the wheels, so use the provided `shell.nix`. Running
`nix-shell` enters a dev shell that supplies those libraries via
`LD_LIBRARY_PATH` and points Qt at the hardware GL driver, so the viewport runs
on the GPU rather than falling back to the llvmpipe software renderer. Create the
`.venv` once from inside the shell — it prepends `.venv/bin` to `PATH`, so
`python` and `pytest` resolve to the venv automatically. The tests run headless
under `QT_QPA_PLATFORM=offscreen`.

## Package (Windows)

PyInstaller bundles the app, including PyMeshLab's native binaries, into a
self-contained folder that needs no Python install. It is a one-directory build —
the libraries sit beside the `.exe` — so startup is near-instant, where a one-file
`.exe` would re-unpack its whole payload on every launch. Cross-compiling is not
possible, so the build runs on a Windows runner in CI
(`.github/workflows/windows-build.yml`), which zips the folder and attaches it to
each run as a downloadable artifact: unzip it and run the `Polycut.exe` inside. To
build locally on Windows:

```sh
pip install -e ".[gui,packaging]"
pyinstaller --noconfirm --clean polycut.spec   # → dist/Polycut/
```
