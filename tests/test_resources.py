"""Bundled-resource path resolution — must work both in dev and when frozen.

PyInstaller's one-file build extracts data to a temp dir exposed as
``sys._MEIPASS``; loading QML from ``__file__``'s directory breaks there. These
tests pin the dev path and the frozen path so the packaged ``.exe`` finds its UI.
"""

from __future__ import annotations

import sys

from polycut import resources


def test_ui_dir_resolves_source_tree_in_dev(monkeypatch):
    """Unfrozen, the UI lives in the real source tree next to the package."""
    monkeypatch.delattr(sys, "frozen", raising=False)

    ui = resources.ui_dir()

    assert ui.name == "ui"
    assert (ui / "Polycut" / "Main.qml").exists()  # the real, runnable UI


def test_ui_dir_resolves_meipass_when_frozen(monkeypatch, tmp_path):
    """Frozen, the UI is read from PyInstaller's extraction dir (``_MEIPASS``)."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    assert resources.ui_dir() == tmp_path / "polycut" / "ui"
