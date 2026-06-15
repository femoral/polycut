# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe — one-file Windows .exe of Polycut.

Two things the stock hooks don't get on their own:

* **PyMeshLab** ships its own native binaries and Qt5 plugins. ``collect_all``
  pulls them in; without it the frozen app imports fine but aborts the moment a
  decimation filter reaches for its missing native libs. (PyMeshLab is Qt5,
  PySide6 is Qt6 — different DLL names, so the two Qts coexist without clashing.)
* **The QML UI** isn't importable Python, so it must be carried as data at the
  same relative path ``polycut/resources.ui_dir()`` expects when frozen.

Build:  ``pyinstaller --noconfirm --clean polycut.spec``  →  ``dist/Polycut.exe``
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

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Polycut",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    # Windowed GUI build — no console. If a packaged build crashes on launch and
    # you need to see the traceback, flip this to True and rebuild.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
