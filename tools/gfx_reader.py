"""Parser for Angelica effect files (.gfx, text "MOXT" format) into plain dicts.

A .gfx is a list of elements (GFXELEMENTID = type). Each element has properties, optional particle
affectors (controllers applied over a particle's life) and keypoints. A keypoint holds a transform /
colour / scale for TimeSpan milliseconds plus controllers (move, rotate, colour fade, curve path...).

Element types: 100 3D decal, 101 screen decal, 102 billboard, 110 trail, 120 point / 121 box /
122 multi-plane / 123 ellipsoid / 124 cylinder / 125 curve particle emitters, 140 ring,
150/151/152 lightning, 160 model, 190 paraboloid, 200 nested gfx, 210/211 grid decals.
"""
from __future__ import annotations

import re

CTRL_KEYS = {
    "Dir", "Vel", "Acc", "Pos", "Axis", "ColorDelta", "ScaleChage", "BufLen", "Amplitude", "WaveLen",
    "Persistence", "OctaveNum", "BaseColor", "Color", "Count", "TimeSpan", "AlphaOnly", "CalcDir", "Scale",
}
KEYPOINT_KEYS = ("InterpolateMode", "TimeSpan", "Position", "Color", "Scale", "Direction", "Rad_2D", "CtrlMethodCount")
NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?(?:e[-+]?\d+)?$", re.I)


def value(text: str):
    text = text.strip()
    parts = [p.strip() for p in text.split(",")]
    if parts and all(NUM_RE.match(p) for p in parts):
        nums = [float(p) if any(c in p for c in ".eE") else int(p) for p in parts]
        return nums[0] if len(nums) == 1 else nums
    return text


def argb(c) -> list[float]:
    """Signed 32-bit ARGB int -> [r, g, b, a] in 0..1."""
    c = int(c) & 0xFFFFFFFF
    return [((c >> 16) & 255) / 255, ((c >> 8) & 255) / 255, (c & 255) / 255, ((c >> 24) & 255) / 255]


class Lines:
    def __init__(self, text: str):
        self.items = []
        for line in text.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                self.items.append((k.strip(), v))
        self.i = 0

    def peek(self):
        return self.items[self.i] if self.i < len(self.items) else (None, None)

    def take(self):
        item = self.peek()
        self.i += 1
        return item


def read_ctrl(lines: Lines, ctype: int) -> dict:
    ctrl: dict = {"t": ctype}
    first = True
    while True:
        k, v = lines.peek()
        if k is None:
            break
        if k in ("StartTime", "EndTime") and (first or k == "EndTime" and "start" in ctrl and "end" not in ctrl):
            lines.take()
            ctrl["start" if k == "StartTime" else "end"] = value(v)
            first = False
            continue
        if k not in CTRL_KEYS:
            break
        lines.take()
        first = False
        val = value(v)
        if k in ctrl:  # repeated keys (curve points, colour / scale steps) become lists
            if not isinstance(ctrl[k], list) or not ctrl.get("_list_" + k):
                ctrl[k] = [ctrl[k]]
                ctrl["_list_" + k] = True
            ctrl[k].append(val)
        else:
            ctrl[k] = val
    for k in [k for k in ctrl if k.startswith("_list_")]:
        del ctrl[k]
    return ctrl


def normalise_ctrl(c: dict) -> dict:
    """Turn raw controller fields into explicit lists for the viewer."""
    t = c["t"]
    out = {"t": t, "s": float(c.get("start", 0) or 0), "e": float(c.get("end", -1) if c.get("end") is not None else -1)}
    if t == 108:  # colour transition: Color0, Count, (Color_i, TimeSpan_i)...
        colors = c.get("Color", [])
        colors = colors if isinstance(colors, list) and colors and isinstance(colors[0], (int, float)) and len(colors) > 1 else [colors]
        spans = c.get("TimeSpan", [])
        spans = spans if isinstance(spans, list) else [spans]
        out["c"] = [argb(x) for x in colors if isinstance(x, (int, float))]
        out["d"] = [float(x) for x in spans]
        out["ao"] = int(c.get("AlphaOnly", 0) or 0)
    elif t == 111:  # scale transition
        scales = c.get("Scale", [])
        scales = scales if isinstance(scales, list) else [scales]
        spans = c.get("TimeSpan", [])
        spans = spans if isinstance(spans, list) else [spans]
        out["k"] = [float(x) for x in scales]
        out["d"] = [float(x) for x in spans]
    elif t == 110:  # curve move
        pos = c.get("Pos", [])
        if pos and not isinstance(pos[0], list):
            pos = [pos]
        out["p"] = pos
        out["cd"] = int(c.get("CalcDir", 0) or 0)
    elif t == 105:
        out["cd"] = c.get("ColorDelta", [0, 0, 0, 0])
    elif t == 106:
        sc = c.get("ScaleChage", [0, 0, 9999])
        out["sc"] = sc if isinstance(sc, list) else [sc, 0, 9999]
    else:
        for src, dst in (("Dir", "dir"), ("Vel", "v"), ("Acc", "a"), ("Pos", "p"), ("Axis", "ax")):
            if src in c:
                out[dst] = c[src]
    return out


def read_ctrls(lines: Lines, count: int) -> list[dict]:
    ctrls = []
    for _ in range(count):
        k, v = lines.peek()
        if k != "CtrlType":
            break
        lines.take()
        ctrls.append(normalise_ctrl(read_ctrl(lines, int(value(v)))))
    return ctrls


def read_keypoint(lines: Lines) -> dict:
    kp: dict = {}
    for key in KEYPOINT_KEYS:
        k, v = lines.peek()
        if k != key:
            break
        lines.take()
        kp[key] = value(v)
    return {
        "m": int(kp.get("InterpolateMode", 0)),
        "d": float(kp.get("TimeSpan", -1)),
        "p": kp.get("Position", [0, 0, 0]),
        "c": argb(kp.get("Color", -1)),
        "s": float(kp.get("Scale", 1)),
        "q": kp.get("Direction", [0, 0, 0, 1]),
        "r": float(kp.get("Rad_2D", 0)),
        "ctrl": read_ctrls(lines, int(kp.get("CtrlMethodCount", 0))),
    }


ELEMENT_PROPS = {
    "Width", "Height", "RotFromView", "OrgPt", "Quota", "ParticleWidth", "ParticleHeight", "3DParticle", "Facing",
    "EmissionRate", "Angle", "Speed", "ParAcc", "AccDir", "Acc", "TTL", "ColorMin", "ColorMax", "ScaleMin",
    "ScaleMax", "RotMin", "RotMax", "IsSurface", "IsBind", "AreaSize", "Radius", "InitRandomTexture", "Pitch",
    "Sects", "OrgAtCenter", "ModelPath", "GfxPath", "PlaySpeed", "OutColor", "LoopFlag", "wNumber", "hNumber",
    "fGridSize", "Loops", "SegLife", "ParIniDir", "IsUseParUV", "NoScale", "ScaleNoOff", "OrgPos1", "OrgPos2",
    "Bind",
}


def parse_gfx(text: str) -> dict:
    head, *blocks = re.split(r"^GFXELEMENTID:", text, flags=re.M)
    root: dict = {"scale": 1.0, "speed": 1.0, "alpha": 1.0, "aabb": None, "elements": []}
    vecs = []
    for k, v in Lines(head).items:
        if k == "DedaultScale":
            root["scale"] = float(value(v))
        elif k == "PlaySpeed":
            root["speed"] = float(value(v))
        elif k == "DefaultAlpha":
            root["alpha"] = float(value(v))
        elif k == "Vec":
            vecs.append(value(v))
    if len(vecs) >= 2:
        root["aabb"] = vecs[:2]

    for block in blocks:
        etype_text, body = block.split("\n", 1) if "\n" in block else (block, "")
        el: dict = {"t": int(etype_text.strip()), "props": {}, "aff": [], "kps": []}
        lines = Lines(body)
        sampler_tex = None
        while True:
            k, v = lines.peek()
            if k is None:
                break
            if k == "KEYPOINTCOUNT":
                lines.take()
                for _ in range(int(value(v))):
                    if lines.peek()[0] != "InterpolateMode":
                        break
                    el["kps"].append(read_keypoint(lines))
                continue
            lines.take()
            if k == "AffectorCount":
                el["aff"] = read_ctrls(lines, int(value(v)))
            elif k == "InterpolateMode" and el["t"] == 125:
                # curve emitter: an inline keypoint whose curve-move controller defines the path
                lines.i -= 1
                kp = read_keypoint(lines)
                curve = next((c for c in kp["ctrl"] if c["t"] == 110), None)
                if curve:
                    el["props"]["curve"] = curve["p"]
            elif k == "Name":
                el["name"] = v.strip()
            elif k == "SrcBlend":
                el["src"] = int(value(v))
            elif k == "DestBlend":
                el["dst"] = int(value(v))
            elif k == "RepeatCount":
                el["rep"] = int(value(v))
            elif k == "RepeatDelay":
                el["repd"] = int(value(v))
            elif k == "TexFile":
                el["tex"] = v.strip()
            elif k == "TexRow":
                el["rows"] = int(value(v))
            elif k == "TexCol":
                el["cols"] = int(value(v))
            elif k == "TexInterval":
                el["ti"] = int(value(v))
            elif k == "ZEnable":
                el["z"] = int(value(v))
            elif k == "StartTime" and "start" not in el:
                el["start"] = float(value(v))
            elif k == "Sampler name=sBase texFile" or k.startswith("Sampler name=sBase"):
                sampler_tex = v.strip()
            elif k in ELEMENT_PROPS:
                el["props"][k] = value(v)
        if not el.get("tex") and sampler_tex:
            el["tex"] = re.sub(r"^gfx\\textures\\", "", sampler_tex, flags=re.I)
        root["elements"].append(el)
    return root
