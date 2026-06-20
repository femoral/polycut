"""Headless convert pipeline — load a Source model, simplify, scale, export DAE.

This package has **no Qt dependency**: it is the test seam. The QML layer reaches
it through a thin bridge object, never the other way around.
"""

from polycut.core.brush import SpatialBrush
from polycut.core.export import (
    ExportResult,
    export_collada,
    export_gltf,
    export_model,
    export_obj,
)
from polycut.core.model import ColourSignal, SceneObject, SourceModel, load_source_model
from polycut.core.orient import UP_AXES, remap_up_axis
from polycut.core.parts import UNASSIGNED_ID, Part, Partition
from polycut.core.picking import (
    add_to_part,
    colour_wand,
    pick_face,
    screen_ray,
    subtract_from_part,
)
from polycut.core.scale import scale_factor, scale_geometry
from polycut.core.segment import face_colour_signal, face_colours, segment, split_by_colour
from polycut.core.transform import Transform
from polycut.core.simplify import (
    ModelSimplifier,
    PreserveOptions,
    simplify_model,
    simplify_parts,
)
from polycut.core.viewport import (
    Attr,
    Buffers,
    VertexAttr,
    build_mesh_buffers,
    build_part_buffers,
    build_part_colours,
)

__all__ = [
    "Attr",
    "Buffers",
    "ColourSignal",
    "ExportResult",
    "ModelSimplifier",
    "Part",
    "Partition",
    "PreserveOptions",
    "SceneObject",
    "SourceModel",
    "SpatialBrush",
    "Transform",
    "UNASSIGNED_ID",
    "VertexAttr",
    "UP_AXES",
    "add_to_part",
    "build_mesh_buffers",
    "build_part_buffers",
    "build_part_colours",
    "colour_wand",
    "export_collada",
    "export_gltf",
    "export_model",
    "export_obj",
    "face_colour_signal",
    "face_colours",
    "load_source_model",
    "pick_face",
    "remap_up_axis",
    "scale_factor",
    "screen_ray",
    "scale_geometry",
    "segment",
    "simplify_model",
    "simplify_parts",
    "split_by_colour",
    "subtract_from_part",
]
