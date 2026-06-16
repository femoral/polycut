"""ModelSimplifier — load the OBJ once, re-cut from the in-memory original (#18).

The stateless :func:`simplify_model` re-reads the 70 MB ``.obj`` from disk on
every cut. :class:`ModelSimplifier` parses it once and re-runs the same
texture-preserving quadric collapse from the pristine in-memory original per
target, so repeated slider settles don't pay the re-parse. These tests pin the
new stateful path to the proven stateless one and to the load-once contract.
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from polycut.core import ModelSimplifier, simplify_model


@pytest.fixture(scope="session")
def loaded_simplifier(sofa_model):
    """Parse the sofa into a ModelSimplifier once; share it across the module."""
    simplifier = ModelSimplifier(sofa_model)
    yield simplifier
    simplifier.close()


@pytest.mark.slow
def test_recut_from_memory_reduces_to_target(loaded_simplifier, sofa_model):
    """A re-cut from the in-memory original lands on the target with UVs intact."""
    target = round(sofa_model.face_count * 0.25)

    result = loaded_simplifier.simplify(target)

    assert result.face_count < sofa_model.face_count
    assert abs(result.face_count - target) <= target * 0.02
    assert result.geometry.visual.uv is not None
    assert len(result.geometry.visual.uv) == len(result.geometry.vertices)
    assert result.has_texture is True
    assert result.texture_path == sofa_model.texture_path


@pytest.mark.slow
def test_recut_matches_stateless_simplify(loaded_simplifier, simplified_sofa, sofa_model):
    """The in-memory re-cut is identical to the stateless disk-reload path.

    Same target, same faithful result the exporter consumes — only the redundant
    parse is gone (ADR-0003 / #18 acceptance: output identical).
    """
    stateless, target = simplified_sofa

    from_memory = loaded_simplifier.simplify(target)

    assert from_memory.face_count == stateless.face_count
    np.testing.assert_array_equal(
        from_memory.geometry.faces, stateless.geometry.faces
    )
    np.testing.assert_allclose(
        from_memory.geometry.vertices, stateless.geometry.vertices
    )
    np.testing.assert_allclose(
        from_memory.geometry.visual.uv, stateless.geometry.visual.uv
    )
    np.testing.assert_allclose(
        from_memory.geometry.vertex_normals, stateless.geometry.vertex_normals
    )


@pytest.mark.slow
def test_parses_obj_from_disk_once(sofa_model, monkeypatch):
    """Construction parses the ``.obj`` once; every later cut re-uses memory."""
    import pymeshlab

    loads = {"n": 0}
    real_load = pymeshlab.MeshSet.load_new_mesh

    def counting_load(self, *args, **kwargs):
        loads["n"] += 1
        return real_load(self, *args, **kwargs)

    monkeypatch.setattr(pymeshlab.MeshSet, "load_new_mesh", counting_load)

    with ModelSimplifier(sofa_model) as simplifier:
        assert loads["n"] == 1  # the single parse, at construction

        light_target = round(sofa_model.face_count * 0.9)
        simplifier.simplify(light_target)
        simplifier.simplify(light_target)

        assert loads["n"] == 1  # re-cuts hit no disk


@pytest.mark.slow
def test_each_cut_starts_from_pristine_original(loaded_simplifier, sofa_model):
    """Every cut runs on the full-res original, never on a prior cut's output."""
    n = sofa_model.face_count
    aggressive_target = round(n * 0.25)
    gentle_target = round(n * 0.6)

    aggressive = loaded_simplifier.simplify(aggressive_target)
    gentle = loaded_simplifier.simplify(gentle_target)

    # Decimation can only remove faces. A gentler target reaching *more* faces
    # than the prior aggressive cut is only possible if this cut restarted from
    # the pristine original rather than from the already-decimated mesh.
    assert gentle.face_count > aggressive.face_count
    assert abs(gentle.face_count - gentle_target) <= gentle_target * 0.02

    # Re-cutting the first target is bit-for-bit repeatable.
    again = loaded_simplifier.simplify(aggressive_target)
    assert again.face_count == aggressive.face_count
    np.testing.assert_array_equal(again.geometry.faces, aggressive.geometry.faces)
    np.testing.assert_allclose(again.geometry.vertices, aggressive.geometry.vertices)


@pytest.mark.slow
def test_recuts_beat_the_disk_reload_baseline(sofa_model):
    """Repeated re-cuts from memory are faster than re-parsing the disk each time.

    The one-time parse is paid at construction (model load), so what the slider
    feels per settle is the re-cut alone — which must beat the stateless
    parse-every-call path by roughly the eliminated re-parses.
    """
    target = round(sofa_model.face_count * 0.5)

    baseline_start = time.perf_counter()
    simplify_model(sofa_model, target)
    simplify_model(sofa_model, target)
    baseline = time.perf_counter() - baseline_start

    with ModelSimplifier(sofa_model) as simplifier:
        recut_start = time.perf_counter()  # construction (the one parse) excluded
        simplifier.simplify(target)
        simplifier.simplify(target)
        recuts = time.perf_counter() - recut_start

    assert recuts < baseline
