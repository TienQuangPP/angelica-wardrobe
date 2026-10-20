"""Pose skinned Angelica models with a skeleton (.bon) and an animation (.stck).

Matrices follow the game (D3D row vectors: v' = v @ M). A skin vertex is moved by
    sum_i  w_i * v @ (init_i @ world_i)
where init is the bone's inverse bind matrix from the .bon and world its posed world matrix.
Vertex bone indices point into the .ski's own bone-name list when it has one (v9+), otherwise
straight into the skeleton.
"""
from __future__ import annotations

import numpy as np

from bon_reader import Bone
from stck_reader import Animation


def quat_matrix(q) -> np.ndarray:
    """D3DXMatrixRotationQuaternion (row-vector convention)."""
    x, y, z, w = np.asarray(q, np.float64) / max(np.linalg.norm(q), 1e-12)
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y + z * w), 2 * (x * z - y * w)],
        [2 * (x * y - z * w), 1 - 2 * (x * x + z * z), 2 * (y * z + x * w)],
        [2 * (x * z + y * w), 2 * (y * z - x * w), 1 - 2 * (x * x + y * y)],
    ])


def _sample(times: np.ndarray, keys: np.ndarray, t: float, quat: bool) -> np.ndarray:
    if len(keys) == 1 or t <= times[0]:
        return keys[0]
    if t >= times[-1]:
        return keys[-1]
    i = int(np.searchsorted(times, t) - 1)
    f = (t - times[i]) / max(times[i + 1] - times[i], 1e-9)
    a, b = keys[i], keys[i + 1]
    if quat:
        if np.dot(a, b) < 0:
            b = -b
        q = a * (1 - f) + b * f
        return q / np.linalg.norm(q)
    return a * (1 - f) + b * f


def local_matrices(bones: list[Bone], anim: Animation | None, t: float = 0.0) -> list[np.ndarray]:
    tracks = {tr.bone: tr for tr in anim.tracks} if anim else {}
    out = []
    for i, b in enumerate(bones):
        tr = tracks.get(i)
        if tr is None:
            out.append(b.relative)
            continue
        m = np.eye(4)
        m[:3, :3] = quat_matrix(_sample(tr.rot_times, tr.rot, t, True))
        m[3, :3] = _sample(tr.pos_times, tr.pos, t, False)
        out.append(m)
    return out


def world_from_local(bones: list[Bone], local: list[np.ndarray]) -> list[np.ndarray]:
    world: list[np.ndarray | None] = [None] * len(bones)

    def get(i):
        if world[i] is None:
            p = bones[i].parent
            world[i] = local[i] if p < 0 else local[i] @ get(p)
        return world[i]

    return [get(i) for i in range(len(bones))]


def skin_matrices(bones: list[Bone], world: list[np.ndarray]) -> list[np.ndarray]:
    return [b.init @ w for b, w in zip(bones, world)]


def bone_index_map(skin_bone_names: list[str], bones: list[Bone]) -> np.ndarray:
    """ski-local bone index -> skeleton index (identity when the .ski has no names)."""
    by_name = {b.name: i for i, b in enumerate(bones)}
    if not skin_bone_names:
        return np.arange(256)
    out = np.zeros(256, np.int64)
    for i, n in enumerate(skin_bone_names):
        out[i] = by_name.get(n, 0)
    return out


def pose_mesh(mesh, index_map: np.ndarray, mats: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    """Return posed (positions, normals) for a skinned mesh."""
    pos = mesh.positions.astype(np.float64)
    nrm = mesh.normals.astype(np.float64)
    if mesh.bone_ids is None:  # rigid mesh bound to one bone
        m = mats[int(index_map[mesh.bone])] if mesh.bone >= 0 else np.eye(4)
        return pos @ m[:3, :3] + m[3, :3], nrm @ m[:3, :3]
    w = np.zeros((len(pos), 4))
    w[:, :3] = mesh.weights
    w[:, 3] = np.clip(1 - mesh.weights.sum(1), 0, 1)
    ids = index_map[mesh.bone_ids.astype(np.int64)]
    stack = np.stack(mats)  # (B, 4, 4)
    out_p = np.zeros_like(pos)
    out_n = np.zeros_like(nrm)
    hom = np.c_[pos, np.ones(len(pos))]
    for k in range(4):
        m = stack[ids[:, k]]  # (N, 4, 4)
        out_p += w[:, k:k + 1] * np.einsum("ni,nij->nj", hom, m)[:, :3]
        out_n += w[:, k:k + 1] * np.einsum("ni,nij->nj", nrm, m[:, :3, :3])
    return out_p, out_n
