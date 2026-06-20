"""Loading a Source model and the import-time stats the UI reports."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import numpy as np
import trimesh

from polycut.core.parts import Partition


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
    initial_partition: Partition | None = None  # source materials → starting Parts

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
    """Load a Source model from any supported format and resolve its materials.

    Accepts GLB/glTF, DAE, OBJ, and geometry-only PLY/STL/OFF, inferring the format
    from the file (ADR-0007). A model that arrives split into materials opens
    already separated into Parts (each material seeds one via the initial
    ``Partition``); a single-material model keeps today's single Unassigned blob.
    Geometry is read unprocessed so the reported face count matches the file exactly
    (no silent vertex-merging before the user has chosen to simplify).
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

    textures, initial_partition = _materials(obj_path, geometry, face_count)
    return SourceModel(
        source_path=obj_path,
        geometry=geometry,
        face_count=face_count,
        object_count=len(meshes),
        textures=textures,
        colour_signal=_colour_signal(geometry, textures=textures),
        objects=objects,
        initial_partition=initial_partition,
    )


def _materials(source_path: Path, geometry, face_count: int):
    """Resolve the source's textures + the initial Partition its materials seed.

    A multi-piece **Scene** (GLB/DAE, multi-material OBJ) opens already separated:
    each geometry is one material → one Part, its texture extracted (embedded images
    materialised beside a temp file, deduped by content). A single **Trimesh** (the
    Meshy OBJ, a PLY/STL/OFF) keeps the single-blob path: its sibling ``.mtl``
    texture, if any, rides on the one Unassigned Part.
    """
    if isinstance(geometry, trimesh.Scene):
        return _scene_materials(geometry)

    texture = _resolve_texture(source_path)  # OBJ sibling .mtl/map_Kd, else None
    textures = (texture,) if texture else ()
    partition = Partition.from_materials(
        np.zeros(face_count, dtype=np.int64),
        material_names=["material"] if textures else [],
        material_textures=[0] if textures else [],
    )
    return textures, partition


def _scene_materials(scene: trimesh.Scene):
    """Each Scene geometry → a material → a Part. Iterates ``Scene.dump()`` — the
    ordered list ``dump(concatenate=True)`` (export's :func:`_single_mesh`) stacks —
    so the partition labels line up face-for-face with the fused mesh, not the dict
    insertion order (which trimesh reorders when it concatenates)."""
    cache: Path | None = None
    by_content: dict[bytes, int] = {}  # dedup shared images to one texture index
    textures: list[Path] = []
    names: list[str] = []
    material_textures: list[int | None] = []
    face_blocks: list[int] = []

    for mesh in scene.dump():
        names.append(mesh.metadata.get("name") or f"Part {len(names) + 1}")
        face_blocks.append(int(mesh.faces.shape[0]))
        image = _material_image(mesh)
        if image is None:
            material_textures.append(None)
            continue
        key = image.tobytes()
        if key not in by_content:
            if cache is None:
                cache = Path(tempfile.mkdtemp(prefix="polycut-tex-"))
            tex_path = cache / f"texture-{len(textures)}.png"
            image.convert("RGB").save(tex_path)
            by_content[key] = len(textures)
            textures.append(tex_path)
        material_textures.append(by_content[key])

    face_materials = np.repeat(np.arange(len(face_blocks)), face_blocks)
    partition = Partition.from_materials(face_materials, names, material_textures)
    return tuple(textures), partition


def _material_image(mesh):
    """The diffuse image of a mesh's material, across glTF and OBJ/Collada flavours."""
    material = getattr(mesh.visual, "material", None)
    if material is None:
        return None
    image = getattr(material, "baseColorTexture", None)  # glTF PBRMaterial
    if image is None:
        image = getattr(material, "image", None)  # OBJ/Collada SimpleMaterial
    return image


def _colour_signal(geometry, textures: tuple) -> ColourSignal:
    """What the Auto-cluster can read: a baked texture, per-vertex colour, or none.

    A usable texture wins; failing that, real per-vertex colour (a vertex-coloured
    PLY/GLB); failing that, geometry-only — the Auto-cluster is disabled and the
    model is carved by hand.
    """
    if textures:
        return ColourSignal.TEXTURE
    meshes = (
        geometry.geometry.values()
        if isinstance(geometry, trimesh.Scene)
        else [geometry]
    )
    if any(getattr(m.visual, "kind", None) == "vertex" for m in meshes):
        return ColourSignal.VERTEX
    return ColourSignal.NONE


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
