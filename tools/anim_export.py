"""Convert Angelica .stck animations to a compact JSON the wardrobe page turns into three.js clips.

Output per clip: {"name", "duration", "tracks": [{"n": bone, "t": [s], "q": [x,y,z,w,...], "pt": [s], "p": [x,y,z,...]}]}
in right-handed glTF space (z mirrored), keyed by bone name so it drives any mesh skinned to a
skeleton with the same bone names.
"""
from __future__ import annotations

import numpy as np

from bon_reader import Bone
from ski_to_glb import decompose, mirror
from skinning import local_matrices, quat_matrix, world_from_local
from stck_reader import Animation


def _yaw_fix(bones: list[Bone], anim: Animation) -> np.ndarray:
    """Row-vector rotation about Y that turns the first frame back to the bind-pose facing."""
    names = [b.name for b in bones]
    if "Bip01 L Thigh" not in names or "Bip01 R Thigh" not in names:
        return np.eye(4)
    li, ri = names.index("Bip01 L Thigh"), names.index("Bip01 R Thigh")
    rest = world_from_local(bones, [b.relative for b in bones])
    posed = world_from_local(bones, local_matrices(bones, anim, 0.0))

    def side(w):
        d = w[li][3, :3] - w[ri][3, :3]
        return np.arctan2(d[2], d[0])

    best, err = np.eye(4), 1e9
    for sign in (1, -1):
        a = sign * (side(posed) - side(rest))
        c, s = np.cos(a), np.sin(a)
        rot = np.eye(4)
        rot[0, 0], rot[0, 2], rot[2, 0], rot[2, 2] = c, -s, s, c
        fixed = [m @ rot for m in posed]
        e = abs(np.angle(np.exp(1j * (side(fixed) - side(rest)))))
        if e < err:
            best, err = rot, e
    return best


def export_clip(name: str, anim: Animation, bones: list[Bone], face_front: bool = True) -> dict:
    fix = _yaw_fix(bones, anim) if face_front else np.eye(4)
    roots = {i for i, b in enumerate(bones) if b.parent < 0}
    tracks = []
    for tr in anim.tracks:
        if not 0 <= tr.bone < len(bones):
            continue
        bone = bones[tr.bone]
        q_out, p_out = [], []
        for q in tr.rot:
            m = np.eye(4)
            m[:3, :3] = quat_matrix(q)
            if tr.bone in roots:
                m = m @ fix
            q_out += decompose(mirror(m))[1]
        for p in tr.pos:
            v = np.append(p, 1.0)
            if tr.bone in roots:
                v = v @ fix
            p_out += [round(float(v[0]), 5), round(float(v[1]), 5), round(float(-v[2]), 5)]
        tracks.append({
            "n": bone.name,
            "t": [round(float(x), 4) for x in tr.rot_times], "q": [round(float(x), 5) for x in q_out],
            "pt": [round(float(x), 4) for x in tr.pos_times], "p": p_out,
        })
    return {"name": name, "duration": round(max(anim.duration, 0.0), 4), "tracks": tracks}
