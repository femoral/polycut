"""Headless convert pipeline — load a Source model, simplify, scale, export DAE.

This package has **no Qt dependency**: it is the test seam. The QML layer reaches
it through a thin bridge object, never the other way around.
"""

from polycut.core.export import ExportResult, export_collada
from polycut.core.model import SourceModel, load_source_model
from polycut.core.simplify import simplify_model

__all__ = [
    "ExportResult",
    "SourceModel",
    "export_collada",
    "load_source_model",
    "simplify_model",
]
