# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe — one-directory Windows bundle of Polycut.

A **one-directory** build (not one-file): the native libs and data sit beside
the EXE in the output folder, so launch is near-instant — a one-file build
re-unpacks its whole ~200 MB archive to a temp dir on every start (issue #17).
CI zips the folder; the user unzips once and runs ``Polycut.exe`` inside it.

Two things the stock hooks don't get on their own:

* **PyMeshLab** ships its own native binaries and Qt5 plugins. ``collect_all``
  pulls them in; without it the frozen app imports fine but aborts the moment a
  decimation filter reaches for its missing native libs. (PyMeshLab is Qt5,
  PySide6 is Qt6 — different DLL names, so the two Qts coexist without clashing.)
* **The QML UI** isn't importable Python, so it must be carried as data at the
  same relative path ``polycut/resources.ui_dir()`` expects when frozen.

Build:  ``pyinstaller --noconfirm --clean polycut.spec``  →  ``dist/Polycut/``
This must run on a Windows runner — PyInstaller cannot cross-compile (issue #5).
"""

from PyInstaller.utils.hooks import collect_all

# binaries + data files + hidden imports for PyMeshLab's native payload
pml_datas, pml_binaries, pml_hiddenimports = collect_all("pymeshlab")

a = Analysis(
    ["polycut/app.py"],
    pathex=["."],
    binaries=pml_binaries,
    datas=[
        ("polycut/ui", "polycut/ui"),  # QML import tree + bundled fonts
        *pml_datas,
    ],
    hiddenimports=[
        *pml_hiddenimports,
        "polycut.bridge",
        "polycut.core",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

# One-dir layout: the EXE carries only the bootloader + bytecode; COLLECT drops
# the native libs and data next to it in dist/Polycut/ — no per-launch unpack.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Polycut",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # Windowed GUI build — no console. If a packaged build crashes on launch and
    # you need to see the traceback, flip this to True and rebuild.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Polycut",
)
