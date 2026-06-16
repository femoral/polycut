"""Shared bridge-test fixtures.

The QtQuick3D bits (``QQuick3DGeometry``, loading the QML shell) need a live
``QGuiApplication``; the rest of the bridge tests drive the ``Processor`` QObject
directly without one. A single offscreen app, created lazily, serves both.
"""

import pytest
from PySide6.QtGui import QGuiApplication


@pytest.fixture(scope="session")
def qapp():
    """One offscreen QGuiApplication for the whole session (only one may exist)."""
    return QGuiApplication.instance() or QGuiApplication([])
