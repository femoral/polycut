"""Loading a Source model and the import-time stats the UI reports."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import trimesh


@dataclass(frozen=True)
class SourceModel:
    """A loaded Source model plus the stats shown after import.

    Holds the trimesh geometry so the export step can reuse it without
    re-reading the file. ``texture_path`` is the baked texture resolved from
    the sibling ``.mtl`` (``None`` when Meshy's texture didn't travel with the
    ``.obj`` — the missing-texture case).
    """

    source_path: Path
    geometry: trimesh.Trimesh | trimesh.Scene
    face_count: int
    object_count: int
    texture_path: Path | None

    @property
    def has_texture(self) -> bool:
        return self.texture_path is not None


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

    return SourceModel(
        source_path=obj_path,
        geometry=geometry,
        face_count=face_count,
        object_count=len(meshes),
        texture_path=_resolve_texture(obj_path),
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
