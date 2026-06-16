"""Preserve toggles — the four flags that steer the texture-preserving collapse (#13).

UV seams / Normals / Boundary edges / Hard edges each map to a PyMeshLab simplify
parameter threaded through ``core``. These pin the observable effect at the public
seam (``simplify_model`` / ``ModelSimplifier``) on small generated fixtures, so the
assertions run fast and deterministically rather than only on the 646k sofa.
"""

from __future__ import annotations

import numpy as np

from polycut.core import ModelSimplifier
from polycut.core.simplify import PreserveOptions, simplify_model


def _same_geometry(a, b) -> bool:
    """Whether two cuts produced the identical vertex set (shape + positions)."""
    va, vb = a.geometry.vertices, b.geometry.vertices
    return va.shape == vb.shape and np.allclose(va, vb)


def _boundary_vertex_count(model) -> int:
    """Vertices left on the unit-grid plane's rim (x or z at 0 or 1)."""
    v = model.geometry.vertices
    x, z = v[:, 0], v[:, 2]
    on_rim = np.isclose(x, 0) | np.isclose(x, 1) | np.isclose(z, 0) | np.isclose(z, 1)
    return int(on_rim.sum())


def test_boundary_on_retains_the_rim_off_collapses_it(open_plane_model):
    """Boundary edges ON keeps the plane's whole open rim; OFF collapses it — the
    AC#2 example, verified at the core seam."""
    kept = simplify_model(
        open_plane_model, 20, PreserveOptions(boundary=True)
    )
    dropped = simplify_model(
        open_plane_model, 20, PreserveOptions(boundary=False)
    )

    assert _boundary_vertex_count(kept) == 32  # the full rim survives
    assert _boundary_vertex_count(dropped) < _boundary_vertex_count(kept)


def test_default_preserve_keeps_uv_normals_and_boundary(open_plane_model):
    """An un-toggled cut reproduces the collapse's long-standing behaviour — UV on,
    boundary on (the rim is held) — so existing cuts are unchanged."""
    defaults = PreserveOptions()
    assert (defaults.uv_seams, defaults.normals, defaults.boundary) == (True, True, True)
    assert defaults.hard_edges is False  # AC: hard edges off by default

    result = simplify_model(open_plane_model, 20)  # no preserve arg → defaults

    assert _boundary_vertex_count(result) == 32  # default boundary=True holds the rim


def test_normals_toggle_changes_the_collapse(creased_cube_model):
    """Toggling Normals (``preservenormal``) changes the output on a creased mesh —
    the flag is honored, not ignored (AC#2)."""
    on = simplify_model(creased_cube_model, 100, PreserveOptions(normals=True))
    off = simplify_model(creased_cube_model, 100, PreserveOptions(normals=False))

    assert not _same_geometry(on, off)


def test_hard_edges_toggle_changes_the_collapse(creased_cube_model):
    """Toggling Hard edges (``planarquadric``) changes the output on a creased mesh,
    so the sharp-crease constraint actually steers the collapse (AC#2)."""
    on = simplify_model(creased_cube_model, 100, PreserveOptions(hard_edges=True))
    off = simplify_model(creased_cube_model, 100, PreserveOptions(hard_edges=False))

    assert not _same_geometry(on, off)


def test_uv_seams_on_retains_per_vertex_uvs(creased_cube_model):
    """With UV seams on, the simplified mesh still carries a per-vertex UV for every
    vertex — the texture survives the collapse (the AC#2 UV example)."""
    result = simplify_model(creased_cube_model, 100, PreserveOptions(uv_seams=True))

    uv = result.geometry.visual.uv
    assert uv is not None
    assert len(uv) == len(result.geometry.vertices)


def test_model_simplifier_honors_preserve(open_plane_model):
    """The stateful re-cut path threads the same flags through: boundary on holds
    the rim, off collapses it — so the toggles work via the slider's re-cut path."""
    with ModelSimplifier(open_plane_model) as simplifier:
        kept = simplifier.simplify(20, PreserveOptions(boundary=True))
        dropped = simplifier.simplify(20, PreserveOptions(boundary=False))

    assert _boundary_vertex_count(kept) == 32
    assert _boundary_vertex_count(dropped) < _boundary_vertex_count(kept)
