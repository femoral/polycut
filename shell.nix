# Dev environment for polycut on NixOS.
#
# PySide6/Qt (incl. QtQuick3D), pymeshlab, and the xcb/wayland platform plugins
# dlopen native libraries that aren't in the PyPI wheels; this shell supplies
# them via LD_LIBRARY_PATH and points Qt at the hardware GL driver (NVIDIA) so the
# viewport runs on the GPU instead of the llvmpipe software fallback.
#
# Usage:
#   nix-shell                              # enter the dev shell (env is set up)
#   python -m polycut.app                  # launch the GUI on the GPU
#   QT_QPA_PLATFORM=offscreen pytest -q -m "not slow"   # run the suite headless
#
# Python deps live in a local .venv (PySide6 etc. from wheels). Create it once,
# inside the shell:
#   python -m venv .venv && .venv/bin/pip install -e '.[gui,dev]'
# The shell prepends .venv/bin to PATH when it exists, so `python` / `pytest`
# resolve to the venv automatically.
#
# git-lfs is on PATH (NixOS ships no system git-lfs): the heavy sofa test fixture
# (tests/fixtures/meshy_sofa/) is stored in Git LFS. The shell configures the LFS
# filters for this repo only; after a fresh clone, run `git lfs pull` once to
# fetch the real fixture (a clone made without git-lfs leaves pointer files).

{ pkgs ? import <nixpkgs> { } }:

let
  # Libraries Qt/PySide6 + pymeshlab dlopen at runtime (absent from the wheels).
  runtimeLibs = with pkgs; [
    stdenv.cc.cc.lib # libstdc++
    zlib
    zstd
    libGL
    libglvnd # GL dispatch (vendor ICD comes from /run/opengl-driver)
    glib
    dbus
    fontconfig
    freetype
    expat
    libxkbcommon
    gmp # pymeshlab's optional e57 plugin links it
    krb5 # libgssapi_krb5.so.2, pulled in by Qt's network stack
    wayland # the wayland platform plugin
    # X / XCB: the xcb platform plugin and its util libs. libxcb-cursor was the
    # missing piece behind "xcb-cursor0 ... needed to load the Qt xcb platform
    # plugin"; the rest are the standard Qt xcb runtime set.
    libx11
    libxcb
    libxext
    libxrender
    libxi
    libxrandr
    libxcursor
    libxfixes
    libsm
    libice
    libxcb-util
    libxcb-wm
    libxcb-image
    libxcb-keysyms
    libxcb-render-util
    libxcb-cursor
  ];
in
pkgs.mkShell {
  # python313 matches the venv interpreter; used to (re)create the venv.
  # git-lfs: the sofa test fixture lives in Git LFS, and NixOS has no system one.
  packages = [ pkgs.python313 pkgs.git-lfs ];

  shellHook = ''
    # /run/opengl-driver/lib (the NixOS hardware-GL vendor dir) must come first,
    # or libglvnd can't find libGLX_nvidia/libEGL_nvidia and Qt silently falls
    # back to llvmpipe (CPU) → very low viewport FPS.
    export LD_LIBRARY_PATH="/run/opengl-driver/lib:${pkgs.lib.makeLibraryPath runtimeLibs}''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    export __GLX_VENDOR_LIBRARY_NAME=nvidia
    # xcb (via XWayland) is the most reliable backend for QtQuick3D + NVIDIA.
    # Override with QT_QPA_PLATFORM=wayland for a native Wayland window, or
    # =offscreen for headless test runs.
    export QT_QPA_PLATFORM="''${QT_QPA_PLATFORM:-xcb}"
    export PYTHONPATH="$PWD''${PYTHONPATH:+:$PYTHONPATH}"
    if [ -d .venv ]; then
      export PATH="$PWD/.venv/bin:$PATH"
    fi
    # Configure the LFS filters for this repo only (idempotent), and deliberately
    # NOT via `git lfs install`: that also installs hooks into git's hooksPath,
    # which can be a shared/global dir, making every other repo invoke git-lfs.
    # The filters alone smudge/clean the LFS-tracked sofa fixture; `git lfs pull`
    # fetches it and `git lfs push` uploads changes (rare — the fixture is static).
    if [ -d .git ] && ! git config --local --get filter.lfs.clean >/dev/null 2>&1; then
      git config --local filter.lfs.clean  "git-lfs clean -- %f"
      git config --local filter.lfs.smudge "git-lfs smudge -- %f"
      git config --local filter.lfs.process "git-lfs filter-process"
      git config --local filter.lfs.required true
    fi
    echo "polycut dev shell · GUI: python -m polycut.app · tests: QT_QPA_PLATFORM=offscreen pytest -q -m 'not slow'"
  '';
}
