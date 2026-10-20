"""Body shape of a customised character (dị dung [Body] sliders), computed like the game does.

Reverse engineered from elementclient.exe:
  * CECPlayer 0xc8d4a0 (standard models; the HD path 0xc8c960 is not used by Kiếm Linh): for each body group k the
    file facedata\\躯干参数\\低模<男|女>\\低模<男|女>_<name>.ini lists bones with 4 flags
    (length, thickness, whole scale, special); the group's slider gives  s = 1 + (v-128)/128 * 0.99
    (0xc8bc70; every factor is 0.99, set in the CECPlayer constructor 0xc73c80);
  * groups / sliders: 头大小 headScale, 上身健壮度 upScale, 腰部围度 waistScale, 上肢围度 armWidth, 下肢围度 legWidth,
    手大小 handScale, 脚大小 footScale, 胸部高低 breastScale (female only);
  * special flag: head group -> thickness sqrt(s) when > 1; breast (female) -> whole += 0.5 t (t = upper body s - 1,
    t > 0) or 0.12 t; upper body / waist / arms (female Bone02) -> whole sqrt(s) when > 1, other bones keep the length
    only for their joint (no segment scaling); legs -> thickness = s.
  * A3DBone (0xefcd30 / 0xefd280 / 0xefc9a0 / 0xefd2c0): a bone's length / thickness scale the segment from its parent
    (applied in the parent's skin matrix along the parent->bone direction; a leaf bone thickens its own segment), the
    length also moves the bone's joint (relative translation * parent whole * length), whole scale is inherited.
The result is {bone name: [length, thickness, whole, segment flag]} for the viewer (tu_do.js applyBodyShape).
"""
from __future__ import annotations

import math
import re

GROUPS = [("头大小", "headScale"), ("上身健壮度", "upScale"), ("腰部围度", "waistScale"), ("上肢围度", "armWidth"),
          ("下肢围度", "legWidth"), ("手大小", "handScale"), ("脚大小", "footScale"), ("胸部高低", "breastScale")]
FACTOR = 0.99


def slider(v: int) -> float:
    return 1.0 + (v - 128) / 128.0 * FACTOR


def read_group(lib, gender: str, name: str) -> list[tuple[str, list[int]]]:
    key = rf"facedata\躯干参数\低模{gender}\低模{gender}_{name}.ini".lower()
    if key not in lib.files:
        return []
    text = lib.read(key).decode("gbk", "replace")
    kv = dict(re.findall(r"^\s*(\w+)\s*=\s*(.*?)\s*$", text, re.M))
    out = []
    for i in range(int(kv.get("count", 0))):
        bone, val = kv.get(f"bone{i}"), kv.get(f"value{i}")
        if bone and val:
            flags = [int(float(x)) for x in val.split(",")][:4]
            out.append((bone, flags + [0] * (4 - len(flags))))
    return out


def body_shape(lib, ini: dict[str, int], female: bool) -> dict[str, list]:
    gender = "女" if female else "男"
    state: dict[str, list] = {}  # bone -> [len, thick, whole, flag]
    s_up = slider(ini.get("upScale", 128))
    for k, (name, key) in enumerate(GROUPS[:8 if female else 7]):
        s = slider(ini.get(key, 128))
        for bone, (f_len, f_thick, f_whole, f_special) in read_group(lib, gender, name):
            st = state.setdefault(bone, [1.0, 1.0, 1.0, 1])
            length = s if f_len else 0.0
            thick = s if f_thick else 0.0
            whole = s if f_whole else st[2]
            flag = 1
            if f_special:
                if k == 0 and thick > 1:
                    thick = math.sqrt(thick)
                elif k == 7 and female:
                    t = s_up - 1
                    if t > 0:
                        whole, length, thick = whole + 0.5 * t, 1 + 0.025 * t, 1 + 0.025 * t
                    else:
                        whole, length, thick = whole + 0.12 * t, 1 + 0.15 * t, 1 + 0.05 * t
                elif k in (1, 2, 3):
                    if female and bone == "Bone02":
                        if whole > 1:
                            whole = math.sqrt(whole)
                    else:
                        flag = 0
            if f_len or f_thick:  # A3DBone::SetLocalScale: 0 keeps the old value
                if length:
                    st[0] = length
                if thick:
                    st[1] = thick
                st[3] = flag
            if f_whole:
                st[2] = whole
    return {b: [round(v, 5) for v in st[:3]] + [st[3]] for b, st in state.items()
            if any(abs(v - 1) > 1e-6 for v in st[:3])}
