"""Shared fixtures for the core seam.

The Meshy sofa is 646k faces; loading and exporting it is the slow part. These
session-scoped fixtures do each once and share the immutable results, so the
suite pays the cost a single time.
"""

from pathlib import Path

import pytest

from polycut.core import export_collada, load_source_model

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
