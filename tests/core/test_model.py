"""SourceModel data model — multi-texture + colour-signal surface (MVP-4 slice A).

ADR-0007 replaces the single shared-texture assumption: the loaded-model
representation carries more than one texture, keeps a derived single-texture view
for the Meshy-parity path, and reports the colour-signal kind the Auto-cluster
gates on. Constructed directly here; the per-format loaders are slice B.
"""

from __future__ import annotations

from pathlib import Path

import trimesh

from polycut.core.model import ColourSignal, SourceModel


def _box(textures=(), colour_signal=ColourSignal.TEXTURE) -> SourceModel:
    box = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    return SourceModel(
        source_path=Path("m.obj"),
        geometry=box,
        face_count=int(box.faces.shape[0]),
        object_count=1,
        textures=textures,
        colour_signal=colour_signal,
    )


def test_source_model_carries_multiple_textures():
    """A multi-textured import exposes every distinct image, so each Part can sample
    its own — the single shared-texture assumption is gone."""
    model = _box(textures=(Path("frame.png"), Path("cushion.png")))

    assert model.textures == (Path("frame.png"), Path("cushion.png"))
    assert model.texture_count == 2
    assert model.has_texture is True


def test_single_texture_model_keeps_the_legacy_single_texture_view():
    """The Meshy case — one baked texture — still answers ``texture_path`` with that
    one image, so the existing single-texture call sites read unchanged (parity)."""
    model = _box(textures=(Path("baked.png"),))

    assert model.texture_path == Path("baked.png")
    assert model.has_texture is True
    assert model.texture_count == 1


def test_geometry_only_model_has_no_texture():
    """A geometry-only import carries no texture: an empty texture list, no
    single-texture view, and the colour signal reads 'none'."""
    model = _box(textures=(), colour_signal=ColourSignal.NONE)

    assert model.textures == ()
    assert model.texture_count == 0
    assert model.has_texture is False
    assert model.texture_path is None


def test_colour_signal_reports_texture_vertex_or_none():
    """The model reports its colour-signal kind, so the Auto-cluster knows whether
    to sample a texture, fall back to per-vertex colour, or disable itself."""
    assert _box(colour_signal=ColourSignal.TEXTURE).colour_signal is ColourSignal.TEXTURE
    assert _box(colour_signal=ColourSignal.VERTEX).colour_signal is ColourSignal.VERTEX
    assert _box(colour_signal=ColourSignal.NONE).colour_signal is ColourSignal.NONE
