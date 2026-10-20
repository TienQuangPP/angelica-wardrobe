"""Parser for Angelica skeleton files (.bon, magic MOXBEKSA).

Header (100 bytes): magic[8], version, numBones, ..., then per bone:
    string name, int flags, int parent, int joint, int numChildren,
    float[16] relative matrix (to parent), float[16] bone-init matrix (inverse bind pose),
    int children[numChildren]
Matrices are D3D row-major with the translation in the last row.
"""
from __future__ import annotations

import re
import struct
from dataclasses import dataclass

import numpy as np

HEADER_SIZE = 100


@dataclass
class Bone:
    name: str
    parent: int
    relative: np.ndarray
    init: np.ndarray
    children: list[int]


def parse_bon(data: bytes) -> list[Bone]:
    if data[:8] != b"MOXBEKSA":
        raise ValueError("not a BON file")
    count = struct.unpack_from("<i", data, 12)[0]
    pos = HEADER_SIZE
    bones = []
    for _ in range(count):
        (n,) = struct.unpack_from("<i", data, pos)
        name = data[pos + 4:pos + 4 + n].decode("gbk", errors="replace")
        pos += 4 + n
        _flags, parent, _joint, n_children = struct.unpack_from("<4i", data, pos)
        pos += 16
        rel = np.array(struct.unpack_from("<16f", data, pos), np.float64).reshape(4, 4)
        init = np.array(struct.unpack_from("<16f", data, pos + 64), np.float64).reshape(4, 4)
        pos += 128
        children = list(struct.unpack_from(f"<{n_children}i", data, pos))
        pos += 4 * n_children
        bones.append(Bone(name, parent, rel, init, children))
    return bones


@dataclass
class Hook:
    name: str
    bone: int
    matrix: np.ndarray  # relative to the bone


HOOK_RE = re.compile(rb"([\x03-\x40])\x00\x00\x00((?:HH|CC)_[^\x00]{1,60}?)([\x00\x01])\x00\x00\x00", re.S)


def parse_hooks(data: bytes, bone_count: int) -> list[Hook]:
    """Hooks (挂点) follow the bones: string name, int type, int bone, float[16] matrix."""
    hooks = []
    for m in HOOK_RE.finditer(data):
        if m.group(1)[0] != len(m.group(2)):
            continue
        pos = m.end()
        bone = struct.unpack_from("<i", data, pos)[0]
        if not -1 <= bone < bone_count or pos + 4 + 64 > len(data):
            continue
        mat = np.array(struct.unpack_from("<16f", data, pos + 4), np.float64).reshape(4, 4)
        hooks.append(Hook(m.group(2).decode("gbk", errors="replace"), bone, mat))
    return hooks


def hook_positions(data: bytes) -> dict[str, np.ndarray]:
    """Bind-pose world position of every hook of a skeleton file."""
    bones = parse_bon(data)
    world = world_matrices(bones)
    out = {}
    for h in parse_hooks(data, len(bones)):
        m = h.matrix if h.bone < 0 else h.matrix @ world[h.bone]
        out[h.name] = m[3, :3].copy()
    for i, b in enumerate(bones):
        out.setdefault(b.name, world[i][3, :3].copy())
    return out


def world_matrices(bones: list[Bone]) -> list[np.ndarray]:
    """Bind-pose world matrices (row-vector convention: world = rel @ parent_world)."""
    out: list[np.ndarray | None] = [None] * len(bones)

    def get(i: int) -> np.ndarray:
        if out[i] is None:
            b = bones[i]
            out[i] = b.relative if b.parent < 0 else b.relative @ get(b.parent)
        return out[i]

    return [get(i) for i in range(len(bones))]
