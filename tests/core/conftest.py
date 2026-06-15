"""Shared fixtures for the core seam.

The Meshy sofa is 646k faces; loading and exporting it is the slow part. These
session-scoped fixtures do each once and share the immutable results, so the
suite pays the cost a single time.
"""

from pathlib import Path

import pytest
import trimesh

from polycut.core import export_collada, load_source_model, simplify_model
from polycut.core.model import SourceModel

DEFAULT_REDUCTION = 0.25  # keep ~25% of faces (the −75% default applied on load)

SOFA = Path(__file__).resolve().parents[1] / "fixtures" / "meshy_sofa" / "model.obj"


@pytest.fixture(scope="session")
def sofa_model():
    return load_source_model(SOFA)


@pytest.fixture(scope="session")
def exported_sofa(sofa_model, tmp_path_factory):
    """Export the sofa once; return (output_path, ExportResult, source_model)."""
    out = tmp_path_factory.mktemp("export") / "sofa.dae"
    result = export_collada(sofa_model, out)
    return out, result, sofa_model


@pytest.fixture
def box_model():
    """A 1×1×1 unit cube — a fast, exact stand-in for geometry/scale tests."""
    box = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    return SourceModel(
        source_path=Path("box.obj"),
        geometry=box,
        face_count=int(box.faces.shape[0]),
        object_count=1,
        texture_path=None,
    )


@pytest.fixture(scope="session")
def simplified_sofa(sofa_model):
    """Simplify the sofa once at the default reduction; return (result, target)."""
    target = round(sofa_model.face_count * DEFAULT_REDUCTION)
    return simplify_model(sofa_model, target), target
