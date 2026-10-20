"""Parser for Angelica skin model files (.ski, magic MOXBIKSA).

Layout (little endian):
    header (108 bytes): magic[8], version, numSkinMesh, numRigidMesh, numMorphSkin, numMorphRigid,
                        numTexture, numMaterial, numSkinBone, minWeight, numSkeBone, ... reserved
    bone names          numSkinBone x string   (only stored by newer versions)
    texture names       numTexture x string    (string = int32 length + GBK bytes)
    materials           numMaterial x ("MATERIAL: " + flag byte + 17 floats + two-sided byte)
    skin meshes         name, texture, material, numVerts, numIndices, vertices, uint16 indices
    rigid meshes        name, bone, texture, material, numVerts, numIndices, vertices, uint16 indices
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

import numpy as np

MAGIC = b"MOXBIKSA"
HEADER_SIZE = 108
MATERIAL_TAG = b"MATERIAL: "


@dataclass
class Material:
    diffuse: tuple[float, float, float, float]
    two_sided: bool


@dataclass
class Mesh:
    name: str
    texture: int
    material: int
    positions: np.ndarray  # (n, 3) float32
    normals: np.ndarray  # (n, 3) float32
    uvs: np.ndarray  # (n, 2) float32
    indices: np.ndarray  # (m,) uint16
    bone: int = -1  # rigid meshes are attached to one bone
    weights: np.ndarray | None = None  # (n, 3) skin weights
    bone_ids: np.ndarray | None = None  # (n, 4) uint8 skeleton bone indices


@dataclass
class Skin:
    version: int
    bones: list[str] = field(default_factory=list)
    textures: list[str] = field(default_factory=list)
    materials: list[Material] = field(default_factory=list)
    meshes: list[Mesh] = field(default_factory=list)


class Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def ints(self, n: int) -> tuple[int, ...]:
        vals = struct.unpack_from(f"<{n}i", self.data, self.pos)
        self.pos += 4 * n
        return vals

    def string(self) -> str:
        (n,) = self.ints(1)
        if not 0 <= n < 1024:
            raise ValueError(f"bad string length {n} at {self.pos - 4}")
        raw = self.data[self.pos:self.pos + n]
        self.pos += n
        return raw.split(b"\0", 1)[0].decode("gbk", errors="replace")

    def array(self, dtype, count: int, width: int) -> np.ndarray:
        size = np.dtype(dtype).itemsize * count * width
        if self.pos + size > len(self.data):
            raise ValueError("array past end of file")
        arr = np.frombuffer(self.data, dtype=dtype, count=count * width, offset=self.pos).reshape(count, width)
        self.pos += size
        return arr


SKIN_VERTEX = np.dtype([("pos", "<f4", 3), ("weights", "<f4", 3), ("bones", "u1", 4),
                        ("normal", "<f4", 3), ("uv", "<f4", 2)])
RIGID_VERTEX = np.dtype([("pos", "<f4", 3), ("normal", "<f4", 3), ("uv", "<f4", 2)])
TANGENT_SIZE = 16  # HD models (version 101) append one float4 tangent per vertex after the indices


def _read_mesh(r: Reader, rigid: bool, tangents: bool) -> Mesh:
    name = r.string()
    bone = r.ints(1)[0] if rigid else -1
    tex, mtl, nv, ni = r.ints(4)
    if not (0 <= nv <= 65536 and 0 <= ni <= 3 * 1_000_000):
        raise ValueError(f"bad mesh counts {nv}/{ni}")
    layout = RIGID_VERTEX if rigid else SKIN_VERTEX
    if r.pos + nv * layout.itemsize + ni * 2 + (nv * TANGENT_SIZE if tangents else 0) > len(r.data):
        raise ValueError("mesh past end of file")
    vtx = np.frombuffer(r.data, dtype=layout, count=nv, offset=r.pos)
    r.pos += nv * layout.itemsize
    idx = np.frombuffer(r.data, dtype="<u2", count=ni, offset=r.pos)
    r.pos += ni * 2
    if tangents:
        r.pos += nv * TANGENT_SIZE
    return Mesh(name, tex, mtl, vtx["pos"].astype(np.float32), vtx["normal"].astype(np.float32),
                vtx["uv"].astype(np.float32), idx.copy(), bone,
                None if rigid else vtx["weights"].astype(np.float32),
                None if rigid else vtx["bones"].copy())


def parse(data: bytes, tangent: bool | None = None) -> Skin:
    """Parse a .ski file. Raises ValueError unless the whole file is consumed exactly."""
    if data[:8] != MAGIC:
        raise ValueError("not a SKI file")
    version, n_skin, n_rigid, n_morph_s, n_morph_r, n_tex, n_mtl, n_bone = struct.unpack_from("<8i", data, 8)
    if n_morph_s or n_morph_r:
        raise ValueError("morph meshes not supported")
    errors = []
    # Bone names are present in newer files only; HD models (version >= 100) carry tangents.
    for with_bones in (True, False) if n_bone else (False,):
        for tangents in ((version >= 100,) if tangent is None else (tangent,)):
            try:
                skin = _parse(data, version, n_skin, n_rigid, n_tex, n_mtl, n_bone if with_bones else 0, tangents)
                return skin
            except (ValueError, struct.error, UnicodeDecodeError) as ex:
                errors.append(f"bones={with_bones} tangents={tangents}: {ex}")
    raise ValueError("; ".join(errors))


def _parse(data, version, n_skin, n_rigid, n_tex, n_mtl, n_bone, tangents) -> Skin:
    r = Reader(data)
    r.pos = HEADER_SIZE
    skin = Skin(version)
    skin.bones = [r.string() for _ in range(n_bone)]
    skin.textures = [r.string() for _ in range(n_tex)]
    for _ in range(n_mtl):
        if data[r.pos:r.pos + len(MATERIAL_TAG)] != MATERIAL_TAG:
            raise ValueError(f"material tag missing at {r.pos}")
        r.pos += len(MATERIAL_TAG) + 1
        vals = struct.unpack_from("<17f", data, r.pos)
        r.pos += 68
        two_sided = data[r.pos] != 0
        r.pos += 1
        skin.materials.append(Material(tuple(vals[0:4]), two_sided))
    for _ in range(n_skin):
        skin.meshes.append(_read_mesh(r, False, tangents))
    for _ in range(n_rigid):
        skin.meshes.append(_read_mesh(r, True, tangents))
    if r.pos != len(data):
        raise ValueError(f"{len(data) - r.pos} trailing bytes")
    for m in skin.meshes:
        if len(m.indices) and int(m.indices.max()) >= len(m.positions):
            raise ValueError(f"mesh {m.name}: index out of range")
    return skin
