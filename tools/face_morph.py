"""Customised faces of the old character creator (dị dung), rebuilt from the client's own data and logic.

Reverse engineered from elementclient.exe (CECFace::Calculate*, CFaceBoneController at 0x5ee000..0x5f0000):
  * Configs\\BoneInit.cfg   the controller's bone order: 46 left / centre bones, 19 centre bones, then the right side
                            (index + 65 mirrors a left bone);
  * Configs\\BoneGroup.cfg  19 bone groups (left side only), Configs\\BonePart.cfg the 3 face parts (上庭/中庭/下庭);
  * Configs\\CustomizeFactor.ini is absent from this client: the factors below are the exe's defaults (0xa323ba);
  * a slider v (0..255) gives  scale = 1 + (v-128)/128 * min(factor, max)  or  offset = (v-128)/128 * min(factor, max);
  * every bone keeps a world matrix (D3D row vectors) that the operations multiply:
        MOVE   M = M * T(v)                     mirror: (-x, y, z)
        ROTATE M = M * T(-c) Rx Ry Rz T(c)      centre 0 = the bone, 1 = selection centre, 2 = pivot bone; mirror (x,-y,-z)
        SCALE  mode 0: M = M * T(-p) S T(p) (the bone itself), mode 1/2: only the position, about the selection centre /
               the pivot bone
  * .eFace shapes (list 59) are per-bone translation deltas applied with a weight.
The skin is then posed with these matrices:  v' = sum w * v * init * M.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from bon_reader import parse_bon, world_matrices
from extract_fashion import norm
from ski_reader import parse

FACTORS = {
    "ScaleFaceH": 0.3, "ScaleFaceV": 0.3, "ScaleUpPart": 0.4, "ScaleMiddlePart": 0.4, "ScaleDownPart": 0.4,
    "OffsetForeheadH": 0.02, "OffsetForeheadV": 0.02, "OffsetForeheadZ": 0.02, "RotateForehead": 1.0, "ScaleForehead": 0.1,
    "OffsetYokeBoneH": 0.01, "OffsetYokeBoneV": 0.01, "OffsetYokeBoneZ": 0.01, "RotateYokeBone": 1.0, "ScaleYokeBone": 0.1,
    "OffsetCheekH": 0.015, "OffsetCheekV": 0.02, "OffsetCheekZ": 0.02, "ScaleCheek": 0.5,
    "OffsetChainV": 0.02, "OffsetChainZ": 0.01, "RotateChain": 1.0, "ScaleChainH": 0.99,
    "OffsetJawH": 0.01, "OffsetJawV": 0.01, "OffsetJawZ": 0.01, "ScaleJawSpecial": 0.01, "ScaleJawH": 0.5, "ScaleJawV": 0.5,
    "ScaleEyeH": 0.7, "ScaleEyeV": 1.0, "RotateEye": 1.0, "OffsetEyeH": 0.01, "OffsetEyeV": 0.01, "OffsetEyeZ": 0.01,
    "ScaleEyeBall": 0.8,
    "ScaleBrowH": 0.4, "ScaleBrowV": 1.0, "RotateBrow": 0.8, "OffsetBrowH": 0.01, "OffsetBrowV": 0.01, "OffsetBrowZ": 0.01,
    "ScaleNoseTipH": 0.8, "ScaleNoseTipV": 0.6, "OffsetNoseTipV": 0.01, "ScaleNoseTipZ": 1.0, "ScaleBridgeTipH": 0.8,
    "OffsetBridgeTipZ": 0.01,
    "ThickUpLip": 1.0, "ThickDownLip": 1.0, "ScaleMouthH": 0.6, "OffsetMouthV": 0.01, "OffsetMouthZ": 0.02,
    "OffsetCornerOfMouthSpecial": 0.02,
    "ScaleEar": 1.0, "OffsetEarV": 0.03,
}
# the cap each Calculate function passes with the factor (min(factor, cap))
CAPS = {"ScaleFaceH": 0.3, "ScaleFaceV": 0.3, "ScaleUpPart": 0.4, "ScaleMiddlePart": 0.4, "ScaleDownPart": 0.4,
        "ScaleEyeH": 0.7, "ScaleEyeV": 1.0, "ScaleEyeBall": 0.8, "ScaleBrowH": 0.4, "ScaleBrowV": 1.0, "RotateBrow": 0.8,
        "ScaleCheek": 0.5, "ScaleChainH": 0.99, "ScaleJawH": 0.5, "ScaleJawV": 0.5, "ScaleNoseTipH": 0.8,
        "ScaleNoseTipV": 0.6, "ScaleNoseTipZ": 1.0, "ScaleBridgeTipH": 0.8, "ThickUpLip": 1.0, "ThickDownLip": 1.0,
        "ScaleMouthH": 0.6, "ScaleEar": 1.0, "ScaleForehead": 0.1, "ScaleYokeBone": 0.1}


def slider_scale(v: int, name: str) -> float:
    f = max(0.0, min(min(FACTORS[name], CAPS.get(name, FACTORS[name])), 0.99))
    return 1.0 + (v - 128) / 128.0 * f


def slider_offset(v: int, name: str) -> float:
    return (v - 128) / 128.0 * min(FACTORS[name], CAPS.get(name, FACTORS[name]))


def T(v) -> np.ndarray:
    m = np.eye(4)
    m[3, :3] = v
    return m


def S(v) -> np.ndarray:
    return np.diag([v[0], v[1], v[2], 1.0])


def rot(axis: str, a: float) -> np.ndarray:
    """D3DXMatrixRotationX/Y/Z (row vectors)."""
    c, s = np.cos(a), np.sin(a)
    m = np.eye(4)
    if axis == "x":
        m[1, 1], m[1, 2], m[2, 1], m[2, 2] = c, s, -s, c
    elif axis == "y":
        m[0, 0], m[0, 2], m[2, 0], m[2, 2] = c, -s, s, c
    else:
        m[0, 0], m[0, 1], m[1, 0], m[1, 1] = c, s, -s, c
    return m


def read_cfg_lines(lib, key: str) -> list[str]:
    return [ln.strip() for ln in lib.read(key).decode("gbk", "replace").splitlines() if ln.strip()]


class FaceController:
    def __init__(self, lib, bon_key: str):
        self.bones = parse_bon(lib.read(bon_key))
        self.bind = world_matrices(self.bones)
        self.by_name = {b.name: i for i, b in enumerate(self.bones)}
        init = read_cfg_lines(lib, r"configs\boneinit.cfg")
        self.order = init[0::2]  # name, flag pairs
        self.M = {n: self.bind[self.by_name[n]].copy() for n in self.order if n in self.by_name}
        self.base = {n: m.copy() for n, m in self.M.items()}
        lines = read_cfg_lines(lib, r"configs\bonegroup.cfg")
        self.groups, i = [], 0
        while i < len(lines):
            count = int(lines[i + 1])
            self.groups.append(lines[i + 2:i + 2 + count])
            i += 2 + count
        lines = read_cfg_lines(lib, r"configs\bonepart.cfg")
        self.parts, i = [], 0
        while i < len(lines):
            count = int(lines[i].split()[0])
            self.parts.append(lines[i + 1:i + 1 + count])
            i += 1 + count
        self.sel: list[int] = []
        self.pivot = 0

    # selection --------------------------------------------------------------------------------------
    def idx(self, name: str) -> int:
        return self.order.index(name)

    def clear(self):
        self.sel = []

    def group(self, g: int):
        for n in self.groups[g]:
            i = self.idx(n)
            if i not in self.sel:
                self.sel.append(i)

    def part(self, p: int):
        self.sel = [self.idx(n) for n in self.parts[p]]

    def add(self, i: int):
        if i not in self.sel:
            self.sel.append(i)

    def right_side(self):
        self.sel = [i + 65 if i < 46 else i for i in self.sel]

    def set_pivot(self, i_or_name):
        self.pivot = self.idx(i_or_name) if isinstance(i_or_name, str) else i_or_name

    def pos(self, i: int) -> np.ndarray:
        return self.M[self.order[i]][3, :3].copy()

    def centre(self) -> np.ndarray:
        pts = [self.pos(i) for i in self.sel if i != 46 and self.order[i] in self.M]
        return np.mean(pts, axis=0) if pts else np.zeros(3)

    def _targets(self, mirror: bool):
        for i in self.sel:
            if i == 46 or self.order[i] not in self.M:
                continue
            yield i, False
            if mirror and i < 46 and self.order[i + 65] in self.M:
                yield i + 65, True

    def _mul(self, i: int, m: np.ndarray):
        n = self.order[i]
        self.M[n] = self.M[n] @ m

    # operations ---------------------------------------------------------------------------------------
    def move(self, v, mirror=True):
        v = np.asarray(v, float)
        for i, mirrored in list(self._targets(mirror)):
            self._mul(i, T(v * [-1, 1, 1] if mirrored else v))

    def rotate(self, v, centre_mode=1, mirror=True):
        v = np.asarray(v, float)
        c = self.centre() if centre_mode == 1 else self.pos(self.pivot) if centre_mode == 2 else None
        for i, mirrored in list(self._targets(mirror)):
            a = v * [1, -1, -1] if mirrored else v
            cc = self.pos(i) if c is None else (c * [-1, 1, 1] if mirrored else c)
            self._mul(i, T(-cc) @ rot("x", a[0]) @ rot("y", a[1]) @ rot("z", a[2]) @ T(cc))

    def scale(self, v, mode=1, mirror=True):
        v = np.asarray(v, float)
        c = self.centre() if mode == 1 else self.pos(self.pivot) if mode == 2 else None
        for i, mirrored in list(self._targets(mirror)):
            p = self.pos(i)
            if mode == 0:  # the bone's own frame: the skin around it grows
                self._mul(i, T(-p) @ S(v) @ T(p))
            else:  # only the bone position, about the centre / pivot
                cc = c * [-1, 1, 1] if mirrored else c
                self._mul(i, T(cc + (p - cc) * v - p))

    def reset_selection(self):
        for i in self.sel:
            n = self.order[i]
            if n in self.base:
                self.M[n] = self.base[n].copy()

    def eyeball(self, s: float, side: int):
        """CFaceBoneController 0x5ef9c0: the eyeball is scaled about (its x, its y, mean z of the inner and outer eye
        corners 眼型011/眼型051), i.e. about the eyelid plane, so a bigger eyeball grows backwards into the head."""
        for i in ([13] if side == 2 else [78]) if side else [13, 78]:
            n = self.order[i]
            if n in self.M:
                p = self.pos(i)
                p[2] = (self.pos(i + 1)[2] + self.pos(i + 5)[2]) * 0.5
                self._mul(i, T(-p) @ S([s, s, s]) @ T(p))

    def shape(self, eface: dict[int, np.ndarray], weight: float = 1.0):
        """eFace: controller bone index -> 4x4 delta (translations in practice)."""
        for i, m in eface.items():
            if i < len(self.order) and self.order[i] in self.M:
                d = np.eye(4) + (m - np.eye(4)) * weight
                self._mul(i, d)

    def skin_matrices(self) -> dict[str, np.ndarray]:
        """Bone name -> init * world, for every bone of the face skeleton."""
        out = {}
        for i, b in enumerate(self.bones):
            world = self.M.get(b.name, self.bind[i])
            out[b.name] = b.init @ world
        return out


def read_eface(data: bytes) -> dict[int, np.ndarray]:
    text = data.decode("gbk", "replace")
    out = {}
    for idx, _name, mat in re.findall(r"(\d+) (\S+)\r?\n((?:\s*[-\d.e]+ [-\d.e]+ [-\d.e]+ [-\d.e]+\r?\n?){4})", text):
        out[int(idx)] = np.array([[float(x) for x in row.split()] for row in mat.strip().splitlines()])
    return out


def customise(lib, ctrl: FaceController, ini: dict[str, int], shape_paths: dict[int, str]) -> None:
    """Run the game's Calculate* steps for one customize .ini (keys of the [..] sections, values 0..255)."""
    g = lambda k, d=128: ini.get(k, d)  # noqa: E731
    sc, of = slider_scale, slider_offset

    def eface(shape_id: int) -> dict[int, np.ndarray]:
        path = shape_paths.get(shape_id)
        key = norm(path).lower() if path else None
        return read_eface(lib.read(key)) if key and key in lib.files else {}

    # BlendFace: two face shapes mixed by blendFaceShape (0..100)
    w = g("blendFaceShape", 50) / 100.0
    ctrl.shape(eface(g("idFaceShape1", 0)), 1 - w)
    ctrl.shape(eface(g("idFaceShape2", 0)), w)
    # Face: outline scaled about the top of the nose
    ctrl.clear(); ctrl.group(1); ctrl.set_pivot(50)
    ctrl.scale([sc(g("scaleFaceH"), "ScaleFaceH"), sc(g("scaleFaceV"), "ScaleFaceV"), 1], 2)
    # Forehead / yoke bone (cheekbones) / cheek
    ctrl.clear(); ctrl.group(3)
    ctrl.move([of(g("offsetForeheadH"), "OffsetForeheadH"), of(g("offsetForeheadV"), "OffsetForeheadV"),
               of(g("offsetForeheadZ"), "OffsetForeheadZ")])
    ctrl.rotate([of(g("rotateForehead"), "RotateForehead"), 0, 0], 1)
    s = sc(g("scaleForehead"), "ScaleForehead")
    ctrl.scale([s, s, s], 0)
    ctrl.clear(); ctrl.group(4)
    ctrl.move([of(g("offsetYokeBoneH"), "OffsetYokeBoneH"), of(g("offsetYokeBoneV"), "OffsetYokeBoneV"),
               of(g("offsetYokeBoneZ"), "OffsetYokeBoneZ")])
    ctrl.rotate([0, 0, of(g("rotateYokeBone"), "RotateYokeBone")], 1)
    s = sc(g("scaleYokeBone"), "ScaleYokeBone")
    ctrl.scale([s, s, s], 0)
    ctrl.clear(); ctrl.group(5)
    ctrl.move([of(g("offsetCheekH"), "OffsetCheekH"), of(g("offsetCheekV"), "OffsetCheekV"),
               of(g("offsetCheekZ"), "OffsetCheekZ")])
    s = sc(g("scaleCheek"), "ScaleCheek")
    ctrl.scale([s, s, s], 0)
    # Chain (chin)
    ctrl.clear(); ctrl.group(6)
    ctrl.move([0, of(g("offsetChainV"), "OffsetChainV"), of(g("offsetChainZ"), "OffsetChainZ")])
    ctrl.rotate([of(g("rotateChain"), "RotateChain"), 0, 0], 1)
    ctrl.set_pivot(48)
    ctrl.scale([sc(g("scaleChainH"), "ScaleChainH"), 1, 1], 2)
    # Jaw
    ctrl.clear(); ctrl.group(2)
    ctrl.move([of(g("offsetJawH"), "OffsetJawH"), of(g("offsetJawV"), "OffsetJawV"), of(g("offsetJawZ"), "OffsetJawZ")])
    ctrl.scale([sc(g("scaleJawH"), "ScaleJawH"), sc(g("scaleJawV"), "ScaleJawV"), 1], 1)
    # 3 parts: lower and middle about the nose bottom, upper about the nose top (the upper part follows the middle)
    ctrl.set_pivot("鼻型060"); ctrl.part(2)
    ctrl.scale([1, sc(g("scaleDown"), "ScaleDownPart"), 1], 2)
    top_before = ctrl.pos(ctrl.idx("鼻型010"))
    ctrl.set_pivot("鼻型060"); ctrl.part(1)
    ctrl.scale([1, sc(g("scaleMiddle"), "ScaleMiddlePart"), 1], 2)
    ctrl.part(0)
    ctrl.move(ctrl.pos(ctrl.idx("鼻型010")) - top_before)
    ctrl.set_pivot("鼻型010"); ctrl.part(0)
    ctrl.scale([1, sc(g("scaleUp"), "ScaleUpPart"), 1], 2)
    # Eyes (eye 1 = the right side bones, eye 2 = the left side, mirrored values)
    ctrl.shape(eface(g("idEyeShape", 0)), 1.0)
    for side, sfx in ((1, ""), (2, "2")):
        sign = 1 if side == 1 else -1
        ctrl.clear(); ctrl.group(7)
        if side == 1:
            ctrl.right_side()
        ctrl.scale([sc(g("scaleEyeH" + sfx), "ScaleEyeH"), sc(g("scaleEyeV" + sfx), "ScaleEyeV"), 1], 1, mirror=False)
        ctrl.rotate([0, 0, sign * of(g("rotateEye" + sfx), "RotateEye")], 1, mirror=False)
        off = [sign * of(g("offsetEyeH" + sfx), "OffsetEyeH"), of(g("offsetEyeV" + sfx), "OffsetEyeV"),
               of(g("offseteyeZ" + sfx, g("offsetEyeZ" + sfx)), "OffsetEyeZ")]
        ctrl.move(off, mirror=False)
        ctrl.clear(); ctrl.group(8)
        if side == 1:
            ctrl.right_side()
        ctrl.reset_selection()
        ctrl.move(off, mirror=False)
        ctrl.eyeball(sc(g("scaleEyeBall" + sfx), "ScaleEyeBall"), side)
    # Brows (same layout as the eyes)
    ctrl.shape(eface(g("idBrowShape", 0)), 1.0)
    for side, sfx in ((1, ""), (2, "2")):
        sign = 1 if side == 1 else -1
        ctrl.clear(); ctrl.group(9)
        if side == 1:
            ctrl.right_side()
        ctrl.scale([sc(g("scaleBrowH" + sfx), "ScaleBrowH"), 1, 1], 1, mirror=False)
        ctrl.scale([1, sc(g("scaleBrowV" + sfx), "ScaleBrowV"), 1], 0, mirror=False)
        ctrl.rotate([0, 0, sign * of(g("rotateBrow" + sfx), "RotateBrow")], 1, mirror=False)
        ctrl.move([sign * of(g("offsetBrowH" + sfx), "OffsetBrowH"), of(g("offsetBrowV" + sfx), "OffsetBrowV"),
                   of(g("offsetBrowZ" + sfx), "OffsetBrowZ")], mirror=False)
    # Nose
    ctrl.shape(eface(g("idNoseTipShape", 0)), 1.0)
    ctrl.shape(eface(g("idNoseBridgeShape", 0)), 1.0)
    ctrl.clear(); ctrl.group(11); ctrl.set_pivot(53)
    ctrl.scale([sc(g("scaleNoseTipH"), "ScaleNoseTipH"), 1, 1], 2)
    s = sc(g("scaleNoseTipV"), "ScaleNoseTipV")
    ctrl.scale([s, s, s], 0)
    ctrl.set_pivot(56)
    ctrl.scale([1, 1, sc(g("scaleNoseTipZ"), "ScaleNoseTipZ")], 2)
    ctrl.move([0, of(g("offsetNoseTipV"), "OffsetNoseTipV"), 0])
    ctrl.clear(); ctrl.group(10); ctrl.set_pivot(50)
    ctrl.scale([sc(g("scaleBridgeTipH"), "ScaleBridgeTipH"), 1, 1], 2)
    # Mouth
    for k in ("idMouthUpLipLine", "idMouthMidLipLine", "idMouthDownLipLine"):
        ctrl.shape(eface(g(k, 0)), 1.0)
    ctrl.clear(); ctrl.group(12); ctrl.set_pivot(32)
    ctrl.scale([1, sc(g("thickUpLip"), "ThickUpLip"), 1], 2)
    ctrl.clear(); ctrl.group(13); ctrl.set_pivot(32)
    ctrl.scale([1, sc(g("thickDownLip"), "ThickDownLip"), 1], 2)
    for side, key in ((1, "scaleMouthH"), (2, "scaleMouthH2")):
        ctrl.clear()
        for gi in (12, 13, 14, 15):
            ctrl.group(gi)
        ctrl.set_pivot(57)
        if side == 1:
            ctrl.right_side()
        ctrl.scale([sc(g(key), "ScaleMouthH"), 1, 1], 2, mirror=False)
    ctrl.clear(); ctrl.group(16); ctrl.add(62)
    ctrl.move([0, of(g("offsetMouthV"), "OffsetMouthV"), of(g("offsetMOuthZ", g("offsetMouthZ")), "OffsetMouthZ")])
    # Ears
    ctrl.shape(eface(g("idEarShape", 0)), 1.0)
    ctrl.clear(); ctrl.group(18); ctrl.set_pivot(4)
    s = sc(g("scaleEar"), "ScaleEar")
    ctrl.scale([s, s, 1], 2)
    ctrl.clear(); ctrl.group(18)
    ctrl.move([0, of(g("offsetEarV"), "OffsetEarV"), 0])


def posed_face(lib, ski_key: str, ctrl: FaceController):
    """Return a function giving the posed (positions, normals) of each mesh of the face skin."""
    skin = parse(lib.read(ski_key))
    mats = ctrl.skin_matrices()
    names = skin.bones or [b.name for b in ctrl.bones]
    stack = np.stack([mats.get(n, np.eye(4)) for n in names] + [np.eye(4)])

    def pose(mesh):
        pos = mesh.positions.astype(np.float64)
        nrm = mesh.normals.astype(np.float64)
        if mesh.bone_ids is None:
            m = stack[min(max(mesh.bone, 0), len(stack) - 1)]
            return pos @ m[:3, :3] + m[3, :3], nrm @ m[:3, :3]
        w = np.zeros((len(pos), 4))
        w[:, :3] = mesh.weights
        w[:, 3] = np.clip(1 - mesh.weights.sum(1), 0, 1)
        ids = np.minimum(mesh.bone_ids.astype(np.int64), len(stack) - 1)
        hom = np.c_[pos, np.ones(len(pos))]
        out_p, out_n = np.zeros_like(pos), np.zeros_like(nrm)
        for k in range(4):
            m = stack[ids[:, k]]
            out_p += w[:, k:k + 1] * np.einsum("ni,nij->nj", hom, m)[:, :3]
            out_n += w[:, k:k + 1] * np.einsum("ni,nij->nj", nrm, m[:, :3, :3])
        return out_p.astype(np.float32), out_n.astype(np.float32)

    return pose


def read_ini(path: Path) -> dict[str, int]:
    text = path.read_bytes().decode("gbk", "replace")
    return {k: int(v) for k, v in re.findall(r"^\s*(\w+)\s*=\s*(-?\d+)", text, re.M)}
