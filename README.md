# Polycut

Desktop tool that turns a high-poly Meshy Source model into a SketchUp-ready
file: simplified to a workable poly count, textured, correctly sized, exported
as Collada (`.dae`). A free alternative to the Transmutr step. See
[`CONTEXT.md`](CONTEXT.md) for the domain language and [`docs/`](docs) for the
design system and ADRs.

## Status

MVP-1 in progress (see issue #1). **Slices 1–4** are in place: open an `.obj` →
resolve its `.mtl` + texture → **simplify** (texture-preserving quadric decimation,
default −75%, with a reduction slider + target-face input) → **scale** (multiplier +
source/target units, baked into the geometry with the unit declared in the `.dae`) →
"Export to SketchUp" writes a textured `.dae` with the texture copied beside it.
**Windows packaging** ships a single-file `.exe` (no install) built in CI.

## Architecture

- `polycut/core/` — headless convert pipeline (load → export). **No Qt**; this
  is the test seam.
- `polycut/bridge/` — the `processor` QObject that exposes `core` to QML.
- `polycut/ui/Polycut/` — QML shell + the `Theme` singleton (single source of
  truth for the design system) + bundled Inter / JetBrains Mono fonts.

## Develop

```sh
python -m venv .venv
.venv/bin/python -m ensurepip
.venv/bin/python -m pip install -e ".[gui,dev]"

.venv/bin/python -m polycut.app      # run the app
.venv/bin/python -m pytest           # run the tests (-m "not slow" to skip the big fixture)
```

> **NixOS:** the `numpy` / `PySide6` / `pymeshlab` wheels are dynamically linked
> and need a standard FHS environment to load their native libraries. Prefix the
> commands above with an FHS wrapper (e.g. `steam-run`) or enable `nix-ld`.
> `pymeshlab` additionally needs `libcom_err.so.2` on the library path — provide
> it from your distro's `e2fsprogs`/`krb5` (e.g. via `LD_LIBRARY_PATH`) if the
> FHS wrapper doesn't already.

## Package (Windows)

PyInstaller bundles the app — and PyMeshLab's native binaries — into a
self-contained folder, no Python install required. It's a one-directory build
(the libs sit beside the `.exe`) so startup is near-instant; a one-file `.exe`
would re-unpack its whole payload on every launch. Cross-compiling isn't
possible, so the build runs on a Windows runner in CI
(`.github/workflows/windows-build.yml`), which zips the folder and attaches it
to each run as a downloadable artifact — unzip it and run the `Polycut.exe`
inside. To build locally on Windows:

```sh
pip install -e ".[gui,packaging]"
pyinstaller --noconfirm --clean polycut.spec   # → dist/Polycut/
```

## License

GPLv3 (simplification uses PyMeshLab — see ADR-0002). Bundled fonts are under
the SIL Open Font License (`polycut/ui/Polycut/fonts/*-OFL.txt`).
