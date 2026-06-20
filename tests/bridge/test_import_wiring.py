"""The Open dialog must offer every format the loader accepts (#38 regression).

MVP-4 slice B taught ``load_source_model`` to read GLB/glTF, DAE, OBJ and the
geometry-only PLY/STL/OFF — but the Open dialog still filtered to ``*.obj``,
so a designer could only pick OBJ files. The processor owns the format list
(single source of truth, mirroring ``exportNameFilters``) and the dialog binds
to it.
"""

from __future__ import annotations

from pathlib import Path

import trimesh

from polycut.bridge.processor import Processor
from polycut.core.model import SourceModel


def test_processor_exposes_the_importable_formats(qapp):
    """The Open-dialog filters cover every format the loader accepts — the
    glTF pair, Collada, OBJ, and the geometry-only trio — not OBJ alone."""
    proc = Processor()

    joined = " ".join(proc.importNameFilters).lower()

    for ext in ("*.glb", "*.gltf", "*.dae", "*.obj", "*.ply", "*.stl", "*.off"):
        assert ext in joined, f"{ext} missing from import filters"


def test_import_filters_lead_with_a_catch_all_for_any_supported_model(qapp):
    """The first filter is a single catch-all listing every supported pattern,
    so the designer can see any importable model without guessing the format."""
    proc = Processor()

    catch_all = proc.importNameFilters[0].lower()

    for ext in ("*.glb", "*.gltf", "*.dae", "*.obj", "*.ply", "*.stl", "*.off"):
        assert ext in catch_all


def _model_with_source(suffix: str) -> SourceModel:
    """A minimal bound model whose on-disk source carries ``suffix`` — enough to
    drive the header's format badge without touching disk."""
    box = trimesh.creation.box()
    return SourceModel(
        source_path=Path(f"chair{suffix}"),
        geometry=box,
        face_count=int(box.faces.shape[0]),
        object_count=1,
    )


def test_format_badge_reflects_the_loaded_models_real_format(qapp):
    """The header format badge names the format the model was loaded from — a GLB
    reads "GLB", not the old hard-coded "OBJ"."""
    proc = Processor()
    proc._model = _model_with_source(".glb")

    assert proc.sourceFormat == "GLB"


def test_format_badge_is_blank_with_no_model(qapp):
    """No model loaded → no format to name."""
    assert Processor().sourceFormat == ""
