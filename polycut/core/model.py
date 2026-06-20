"""Loading a Source model and the import-time stats the UI reports."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import trimesh


class ColourSignal(Enum):
    """How the Auto-cluster reads a model's colour (ADR-0007).

    ``TEXTURE`` — sample a baked UV texture; ``VERTEX`` — fall back to per-vertex
    colour; ``NONE`` — geometry-only, no colour to cluster on (the Auto-cluster is
    disabled and the model is carved only by hand).
    """

    TEXTURE = "texture"
    VERTEX = "vertex"
    NONE = "none"


@dataclass(frozen=True)
class SceneObject:
    """One row of the Scene Outliner: an object in the loaded file + its faces."""

    name: str
    face_count: int


@dataclass(frozen=True)
class SourceModel:
    """A loaded Source model plus the stats shown after import.

    Holds the trimesh geometry so the export step can reuse it without re-reading
    the file. ``textures`` are the model's distinct baked images (ADR-0007's
    multi-texture model, replacing the single shared-texture assumption); each Part
    references one by index. Empty when no texture travelled with the file (the
    missing-texture / geometry-only case). ``colour_signal`` is what the
    Auto-cluster reads. ``texture_path`` is the single-texture view the Meshy path
    keeps for parity — the first image, or ``None``.
    """

    source_path: Path
    geometry: trimesh.Trimesh | trimesh.Scene
    face_count: int
    object_count: int
    textures: tuple[Path, ...] = ()
    colour_signal: ColourSignal = ColourSignal.TEXTURE
    objects: tuple[SceneObject, ...] = ()  # the model's composition, for the outliner

    @property
    def texture_path(self) -> Path | None:
        """The first baked texture — the single-texture view kept for the Meshy path."""
        return self.textures[0] if self.textures else None

    @property
    def has_texture(self) -> bool:
        return bool(self.textures)

    @property
    def texture_count(self) -> int:
        return len(self.textures)


def load_source_model(obj_path) -> SourceModel:
    """Load a Meshy ``.obj`` and resolve its sibling ``.mtl`` + texture.

    Geometry is read unprocessed so the reported face count matches the file
    exactly (no silent vertex-merging before the user has chosen to simplify).
    """
    obj_path = Path(obj_path)
    geometry = trimesh.load(obj_path, process=False)

    meshes = (
        list(geometry.geometry.values())
        if isinstance(geometry, trimesh.Scene)
        else [geometry]
    )
    face_count = sum(int(m.faces.shape[0]) for m in meshes)

    objects = tuple(
        SceneObject(
            name=obj_path.stem if i == 0 else f"{obj_path.stem}.{i}",
            face_count=int(m.faces.shape[0]),
        )
        for i, m in enumerate(meshes)
    )

    texture = _resolve_texture(obj_path)
    return SourceModel(
        source_path=obj_path,
        geometry=geometry,
        face_count=face_count,
        object_count=len(meshes),
        textures=(texture,) if texture else (),
        colour_signal=ColourSignal.TEXTURE if texture else ColourSignal.NONE,
        objects=objects,
    )


def _resolve_texture(obj_path: Path) -> Path | None:
    """Find the baked texture beside the OBJ via its ``.mtl`` ``map_Kd``."""
    directory = obj_path.parent
    for mtl_name in _mtllib_names(obj_path):
        mtl_path = directory / mtl_name
        if not mtl_path.exists():
            continue
        for tex_name in _map_kd_names(mtl_path):
            tex_path = directory / tex_name
            if tex_path.exists():
                return tex_path
    return None


def _mtllib_names(obj_path: Path) -> list[str]:
    """The ``.mtl`` filenames an OBJ references (header-only; OBJs are huge)."""
    names: list[str] = []
    with obj_path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            if line.startswith("mtllib"):
                names.extend(line.split()[1:])
            elif line.startswith(("v ", "vt ", "f ", "o ", "g ")):
                break  # geometry has started; mtllib only appears in the header
    return names


def _map_kd_names(mtl_path: Path) -> list[str]:
    """The diffuse-texture filenames (``map_Kd``) declared in an ``.mtl``."""
    names: list[str] = []
    with mtl_path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            parts = line.split()
            if parts and parts[0] == "map_Kd":
                names.append(parts[-1])  # trailing token is the filename
    return names
