"""Where to find bundled resources (the QML UI, fonts) at runtime.

In development the package runs from the source tree, so resources sit next to
it. In a PyInstaller one-file build the app is *frozen*: the bundle is unpacked
to a temporary directory exposed as ``sys._MEIPASS``, and that — not the source
tree, which isn't present on the user's machine — is where the data lives.
"""

from __future__ import annotations

import sys
from pathlib import Path


def base_dir() -> Path:
    """Root that holds bundled data: PyInstaller's extraction dir when frozen,
    otherwise the install/source root that contains the ``polycut`` package."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


def ui_dir() -> Path:
    """Directory holding the QML import tree (the ``Polycut`` module + fonts)."""
    return base_dir() / "polycut" / "ui"
