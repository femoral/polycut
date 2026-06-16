"""Headless convert pipeline — load a Source model, simplify, scale, export DAE.

This package has **no Qt dependency**: it is the test seam. The QML layer reaches
it through a thin bridge object, never the other way around.
"""

from polycut.core.export import ExportResult, export_collada
from polycut.core.model import SceneObject, SourceModel, load_source_model
from polycut.core.orient import UP_AXES, remap_up_axis
from polycut.core.scale import scale_factor, scale_geometry
from polycut.core.simplify import ModelSimplifier, PreserveOptions, simplify_model
from polycut.core.viewport import MeshBuffers, build_mesh_buffers

__all__ = [
    "ExportResult",
    "MeshBuffers",
    "ModelSimplifier",
    "PreserveOptions",
    "SceneObject",
    "SourceModel",
    "UP_AXES",
    "build_mesh_buffers",
    "export_collada",
    "load_source_model",
    "remap_up_axis",
    "scale_factor",
    "scale_geometry",
    "simplify_model",
]
