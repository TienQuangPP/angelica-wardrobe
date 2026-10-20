"""Prepare the data of the wardrobe page (tu_do.html): a copy of the in-game "Thu thập" fashion window
with a Kiếm Linh (剑灵) character.

Usage: py tools/build_wardrobe.py [--out=<data>\\3D] [--force | --force-parts | --no-convert]

Needs the outputs of extract_fashion.py, ski_to_glb.py (1_trang_phuc + 3_toc_dau glbs under --out)
and writes <out>/tu_do/:
    base/      Kiếm Linh body, faces and default hair (.glb)
    scene/     the dress-up scene (新粉色换装场景) as .glb
    ui/        window textures from the game (PNG)
    icons/     shop icons of the sets
    catalog.json
Effects go to <out>/fx like build_fx.py.
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import ski_to_glb  # noqa: E402
from anim_export import export_clip  # noqa: E402
from bon_reader import hook_positions, parse_bon, parse_hooks, world_matrices  # noqa: E402
from ski_reader import parse  # noqa: E402
from stck_reader import parse_stck  # noqa: E402
from build_fx import HOOK_FALLBACK, Exporter, export_effects, match_set_effects, place_effects  # noqa: E402
from body_shape import body_shape  # noqa: E402
from build_sets import BODIES, LOD_RE, classify, collect_sets  # noqa: E402
from extract_fashion import OUT, norm  # noqa: E402
from tghm_paths import ELEMENT  # noqa: E402
from face_morph import FaceController, customise, posed_face  # noqa: E402
from game_data import RARITY, RARITY_COLOR  # noqa: E402
from game_data import load as load_game_data  # noqa: E402
from gfx_reader import value  # noqa: E402

CHARACTERS = {
    "nu": {"label": "Kiếm Linh nữ", "gender": "女", "body_type": "女通用", "folder": r"models\players\形象\剑灵女",
           "body": "剑灵女", "head": "剑灵女头", "hair_offset": 1.570, "styles": r"facedata\灵族女\头发模型库"},
    "nam": {"label": "Kiếm Linh nam", "gender": "男", "body_type": "男通用", "folder": r"models\players\形象\剑灵男",
            "body": "剑灵男", "head": "剑灵男头", "hair_offset": 1.740, "styles": r"facedata\灵族男\头发模型库"},
}
# Actions offered in the wardrobe (track file names without the class prefix variants)
ACTIONS = [
    ("Đứng", ["站立_通用"]),
    ("Đứng (đăng nhập)", ["{body}_登陆站立"]),
    ("Nghỉ", ["长休闲动作身体_通用", "休闲_通用", "休闲"]),
    ("Múa 1", ["休闲舞蹈1"]),
    ("Múa 2", ["休闲舞蹈2"]),
    ("Tĩnh", ["{body}站立静帧", "站立静帧"]),
]
# The fashion window's own stage (cherry tree, stone lanterns, round platform); pink = day, blue = night.
SCENES = {
    "pink": r"models\场景动画模型\2020\换装场景\换装场景粉",
    "blue": r"models\场景动画模型\2020\换装场景\换装场景蓝",
}
UI_FOLDERS = [r"surfaces\version02\系统\时装图鉴", r"surfaces\version02\按钮\通用按钮", r"surfaces\version02\系统\时装商城\调色板",
              r"surfaces\时装套装标签"]
SLOT_ORDER = ["top", "bottom", "wrist", "shoes"]
DEFAULT_PIECES = {"top": "时装默认上衣", "bottom": "时装默认裤子", "wrist": "时装默认护腕", "shoes": "时装默认鞋子"}
SLOT_LABEL = {"hair": "Tóc", "top": "Áo", "bottom": "Quần", "wrist": "Oản", "shoes": "Giày"}
HAIR_MESH_RE = re.compile(r"头发|发饰|头饰|hair", re.I)


def is_hair(mesh, tex: str) -> bool:
    return bool(HAIR_MESH_RE.search(tex) or HAIR_MESH_RE.search(mesh.name))


def write_glb(dest: Path, parts: list[tuple[str, str, object]]) -> bool:
    glb = ski_to_glb.GlbBuilder()
    mats, warns = {}, []
    n = sum(ski_to_glb.add_skin(glb, key, name, mats, warns, keep) for key, name, keep in parts)
    if not n:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(glb.finish())
    return True


_SKELETONS: dict = {}


def skeletons(cid: str):
    """(base skeleton used by the animations, extended skeleton with the cloth bones) of a character."""
    if cid not in _SKELETONS:
        lib = ski_to_glb._lib
        ch = CHARACTERS[cid]
        base = parse_bon(lib.read(rf"{ch['folder']}\躯干\{ch['body']}.bon".lower()))
        ex_key = rf"{ch['folder']}\躯干\{ch['body']}ex.bon".lower()
        ex = parse_bon(lib.read(ex_key)) if ex_key in lib.files else base
        _SKELETONS[cid] = (base, ex)
    return _SKELETONS[cid]


def convert_job(job: tuple, out_root: str) -> tuple[str, int, str]:
    """Write one skinned glb. job = (dest relative to out_root, ski key, character id, mode)."""
    dest, key, cid, mode = job
    try:
        base, ex = skeletons(cid)
        glb = ski_to_glb.GlbBuilder()
        skel = glb.add_skeleton(ex)
        skel.base_names = [b.name for b in base]
        keep = offset = None
        alpha = "auto"
        if mode == "hair":  # fashion hair: modelled around the neck point, rides on the head bone
            skel.rigid = "Bip01 Head"
            offset = (0, CHARACTERS[cid]["hair_offset"], 0)
        elif mode == "face":
            keep = lambda m, t: not is_hair(m, t)  # noqa: E731
        elif mode == "basehair":
            keep = is_hair
        elif mode in ("part", "body"):  # fashion shader: alpha is the dye / skin-colour mask, never a hole
            alpha = "dye"
        n = ski_to_glb.add_skin(glb, key, Path(key).stem, {}, [], keep, offset, skel, alpha)
        if n:
            path = Path(out_root) / dest
            path.parent.mkdir(parents=True, exist_ok=True)
            with open("\\\\?\\" + str(path.resolve()), "wb") as fh:
                fh.write(glb.finish())
        return dest, n, ""
    except Exception as ex_:
        return dest, 0, f"{type(ex_).__name__}: {ex_}"


def convert_batch(batch: list, out_root: str) -> list:
    return [convert_job(j, out_root) for j in batch]


def build_base(lib, jobs: list) -> dict:
    """Body, faces and default hair of each character, skinned (paths relative to tu_do/)."""
    base = {}
    for cid, ch in CHARACTERS.items():
        folder = ch["folder"]
        jobs.append((f"tu_do/sk/{cid}/base/body_d.glb", rf"{folder}\躯干\{ch['body']}.ski".lower(), cid, "body"))
        faces = []
        for i in range(1, 6):
            head = rf"{folder}\头\{ch['head']}{i}.ski".lower()
            if head not in lib.files:
                continue
            jobs.append((f"tu_do/sk/{cid}/base/face{i}.glb", head, cid, "face"))
            jobs.append((f"tu_do/sk/{cid}/base/hair{i}.glb", head, cid, "basehair"))
            faces.append({"face": f"sk/{cid}/base/face{i}.glb", "hair": f"sk/{cid}/base/hair{i}.glb"})
        # hairstyles of the race's appearance editor (dị dung)
        styles = []
        for key in lib.under(ch["styles"].lower()):
            if key.endswith(".ski") and key.count("\\") == ch["styles"].count("\\") + 1:
                stem = Path(key).stem
                jobs.append((f"tu_do/sk/{cid}/style/{stem}.glb", key, cid, "hair"))
                num = re.search(r"(\d+)$", stem)
                styles.append({"name": f"Kiểu {int(num.group(1))}" if num else stem, "glb": f"sk/{cid}/style/{stem}.glb"})
        base[cid] = {"label": ch["label"], "body": f"sk/{cid}/base/body_d.glb", "faces": faces, "styles": styles,
                     "hairOffset": ch["hair_offset"], "anims": f"anim_{cid}.json"}
    return base


USERDATA = ELEMENT / "userdata" / "character" / "customize"
PRESETS = {"nu": (81, r"facedata\灵族女\预定义\剑灵女预定义1.ini"), "nam": (80, r"facedata\灵族男\预定义\剑灵男自定义1.ini")}


def argb(v: int) -> list[int]:
    v &= 0xFFFFFFFF
    return [(v >> 16) & 255, (v >> 8) & 255, v & 255]


def read_preset(lib, gd: dict, exporter, cid: str, ch: dict, base: dict, wd: Path) -> dict | None:
    """The sample character of the creator (dị dung): the newest appearance saved in the game
    (userdata\\character\\customize\\<class><gender>\\*.ini, 8 = Kiếm Linh) or the class's first preset."""
    folder, fallback = PRESETS[cid]
    saved = sorted((USERDATA / str(folder)).glob("*.ini"), key=lambda p: p.stat().st_mtime, reverse=True) \
        if (USERDATA / str(folder)).is_dir() else []
    if saved:
        text, source = saved[0].read_bytes().decode("gbk", "replace"), saved[0].stem
    elif fallback.lower() in lib.files:
        text, source = lib.read(fallback.lower()).decode("gbk", "replace"), Path(fallback).stem
    else:
        return None
    ini = {k: int(v) for k, v in re.findall(r"^\s*(\w+)\s*=\s*(-?\d+)", text, re.M)}
    preset: dict = {"name": source, "_ini": ini}
    tex = gd["textures"].get(ini.get("idFaceTex", 0))
    num = re.search(r"(\d+)\.dds$", tex["paths"][0], re.I) if tex and tex["paths"] else None
    if num and 1 <= int(num.group(1)) <= len(base["faces"]):
        preset["face"] = int(num.group(1))
    hair = gd["hairs"].get(ini.get("idHairModel", 0))
    if hair and hair["paths"]:
        stem = Path(norm(hair["paths"][0])).stem.lower()
        preset["hairStyle"] = next((s["glb"] for s in base["styles"] if Path(s["glb"]).stem.lower() == stem), None)
    if "colorHair" in ini:
        preset["hair"] = argb(ini["colorHair"])
    if ini.get("colorEyeBall"):
        preset["eye"] = argb(ini["colorEyeBall"])
    # eyeball textures of the creator: b = iris (times the pupil colour), a = highlight drawn over it by its alpha
    ball = gd["textures"].get(ini.get("idEyeBallTex", 0))
    for path in (ball or {}).get("paths", []):
        key = norm(path).lower()
        layer = "eyeHigh" if re.search(r"a\d+\.dds$", key) else "eyeBase" if re.search(r"b\d+\.dds$", key) else None
        if layer and key in lib.files:
            rel = f"face/{cid}_{layer}.png"
            (wd / rel).parent.mkdir(parents=True, exist_ok=True)
            Image.open(io.BytesIO(lib.read(key))).convert("RGBA").save(wd / rel)
            preset[layer] = rel
    eye = gd["third_eye"].get(ini.get("idThirdEye", 0))
    gfx = next((p for p in (eye or {}).get("paths", []) if p.lower().endswith(".gfx")), None)
    if gfx:
        key = norm(gfx).lower()
        key = key if key.startswith("gfx\\") else "gfx\\" + key
        face_bon = rf"models\face\{ch['body']}标准脸\{ch['body']}标准脸1.bon".lower()
        if key in lib.files and face_bon in lib.files:
            pos = hook_positions(lib.read(face_bon)).get("HH_额饰")
            if pos is not None:  # forehead hook of the face skeleton (face space) -> body space
                p = [round(float(pos[0]), 4), round(float(pos[1]) + ch["hair_offset"], 4), round(float(pos[2]), 4)]
                preset["fx"] = [{"u": exporter.export(key), "p": p, "n": Path(key).stem, "h": "HH_额饰", "b": "Bip01 Head"}]
    # [Body] sliders: per-bone length / thickness / whole scale (body_shape.py)
    shape = body_shape(lib, ini, female=cid == "nu")
    if shape:
        preset["body"] = shape
    return preset


def build_custom_face(lib, gd: dict, cid: str, ch: dict, preset: dict, wd: Path) -> str | None:
    """The preset's face with the creator's sliders and shapes applied (face_morph.py), baked into a glb that rides
    on the head bone like the default head. The game builds it on models\\face\\<class>标准脸<n> (114 face bones)."""
    face_no = preset.get("face", 1)
    ski = rf"models\face\{ch['body']}标准脸\{ch['body']}标准脸{face_no}.ski".lower()
    bon = ski[:-4] + ".bon"
    if ski not in lib.files or bon not in lib.files:
        return None
    ctrl = FaceController(lib, bon)
    shapes = {i: next((p for p in r["paths"] if p.lower().endswith(".eface")), None) for i, r in gd["face_shapes"].items()}
    customise(lib, ctrl, preset["_ini"], shapes)
    base, ex = skeletons(cid)
    glb = ski_to_glb.GlbBuilder()
    skel = glb.add_skeleton(ex)
    skel.base_names = [b.name for b in base]
    skel.rigid = "Bip01 Head"  # face space -> the head, offset like the default head (fitted: 1.5701 for 剑灵女)
    n = ski_to_glb.add_skin(glb, ski, "face", {}, [], None, (0, ch["hair_offset"], 0), skel, "auto",
                            posed_face(lib, ski, ctrl))
    if not n:
        return None
    # the forehead ornament hangs on HH_额饰 of 鼻型010: it follows that bone's new place
    hooks = [h for h in parse_hooks(lib.read(bon), len(ctrl.bones)) if h.name == "HH_额饰" and h.bone >= 0]
    if hooks and preset.get("fx"):
        h = hooks[0]
        bone = ctrl.bones[h.bone].name
        p = (h.matrix @ ctrl.M.get(bone, ctrl.bind[h.bone]))[3, :3]
        for f in preset["fx"]:
            if f.get("h") == "HH_额饰":
                f["p"] = [round(float(p[0]), 4), round(float(p[1]) + ch["hair_offset"], 4), round(float(p[2]), 4)]
    rel = f"sk/{cid}/base/face_custom.glb"
    (wd / rel).parent.mkdir(parents=True, exist_ok=True)
    (wd / rel).write_bytes(glb.finish())
    return rel


PET_IDLE = ("待机", "站立", "休闲")


def build_pet(lib, wd: Path, ecm: str) -> dict | None:
    """Companion pet of a set (Linh sủng): skinned glb on its own skeleton + its idle animation."""
    key = norm(ecm).lower()
    if key not in lib.files:
        return None
    folder, stem = key.rsplit("\\", 1)[0], Path(key).stem
    text = lib.read(key).decode("gbk", "replace")
    smd = re.search(r"SkinModelPath:\s*(.+)", text)
    if smd:  # the .smd names the skeleton / skin; they sit next to it
        stem = Path(norm(smd.group(1).strip())).stem.lower()
    ski, bon = f"{folder}\\{stem}.ski", f"{folder}\\{stem}.bon"
    if ski not in lib.files or bon not in lib.files:
        return None
    rel = f"pet/{re.sub(r'[^0-9A-Za-z一-鿿]+', '_', Path(key).stem)}"
    bones = parse_bon(lib.read(bon))
    glb = ski_to_glb.GlbBuilder()
    skel = glb.add_skeleton(bones)
    skel.base_names = [b.name for b in bones]
    if not ski_to_glb.add_skin(glb, ski, stem, {}, [], None, None, skel):
        return None
    (wd / "pet").mkdir(parents=True, exist_ok=True)
    (wd / f"{rel}.glb").write_bytes(glb.finish())
    tracks = [k for k in lib.under(f"{folder}\\tcks_{stem}") if k.endswith(".stck")]
    idle = next((k for word in PET_IDLE for k in tracks if word in Path(k).stem and "妖兽" not in k), None)
    clips = []
    if idle:
        try:
            clips.append(export_clip("idle", parse_stck(lib.read(idle)), bones, face_front=False))
        except ValueError as ex_:
            print("  pet anim skip", idle, ex_)
    (wd / f"{rel}.json").write_text(json.dumps({"clips": clips}, separators=(",", ":")), encoding="utf-8")
    return {"glb": f"{rel}.glb", "anims": f"{rel}.json"}


def export_animations(lib, wd: Path) -> None:
    for cid, ch in CHARACTERS.items():
        base, _ = skeletons(cid)
        clips = []
        for label, names in ACTIONS:
            for name in names:
                key = rf"{ch['folder']}\躯干\tcks_{ch['body']}\{name.format(body=ch['body'])}.stck".lower()
                if key not in lib.files:
                    continue
                try:
                    clip = export_clip(label, parse_stck(lib.read(key)), base)
                except ValueError as ex_:
                    print("  anim skip", key, ex_)
                    continue
                clips.append(clip)
                break
        (wd / f"anim_{cid}.json").write_text(json.dumps({"clips": clips}, ensure_ascii=False, separators=(",", ":")),
                                             encoding="utf-8")
        print(f"  {ch['label']}: actions {[c['name'] for c in clips]}")


def ground_height(mesh, x: float, z: float) -> float | None:
    """Highest point of a mesh at (x, z), by barycentric test on every triangle."""
    p, tri = mesh.positions, mesh.indices[: len(mesh.indices) // 3 * 3].reshape(-1, 3)
    best = None
    for a, b, c in tri:
        A, B, C = p[a], p[b], p[c]
        v0, v1, v2 = C[[0, 2]] - A[[0, 2]], B[[0, 2]] - A[[0, 2]], np.array([x, z]) - A[[0, 2]]
        d00, d01, d11, d20, d21 = v0 @ v0, v0 @ v1, v1 @ v1, v2 @ v0, v2 @ v1
        den = d00 * d11 - d01 * d01
        if abs(den) < 1e-12:
            continue
        u, v = (d11 * d20 - d01 * d21) / den, (d00 * d21 - d01 * d20) / den
        if u >= -1e-4 and v >= -1e-4 and u + v <= 1 + 1e-4:
            y = float(A[1] + u * (C[1] - A[1]) + v * (B[1] - A[1]))
            best = y if best is None else max(best, y)
    return best


def build_scene(lib, wd: Path, exporter: Exporter, name: str, base: str) -> dict:
    """Scene glb + its effects. 'offset' is the root-bone translation the game applies to the scene and
    'stage' the top centre of the round platform (both in game coordinates)."""
    ski_key = base.lower() + ".ski"
    ski_to_glb.MAX_TEXTURE = 1024
    write_glb(wd / "scene" / f"{name}.glb", [(ski_key, "scene", None)])
    ski_to_glb.MAX_TEXTURE = None
    offset = [0.0, 0.0, 0.0]
    folder = base.lower().rsplit("\\", 1)[0]
    bons = [k for k in lib.under(folder) if k.endswith(".bon")]
    bon = base.lower() + ".bon" if base.lower() + ".bon" in lib.files else (bons[0] if bons else None)
    if bon:
        bones = parse_bon(lib.read(bon))
        if bones:
            offset = [round(float(v), 4) for v in world_matrices(bones)[0][3, :3]]
    skin = parse(lib.read(ski_key))
    stage = [0.0, 0.0, 0.0]
    for m in skin.meshes:
        tex = skin.textures[m.texture] if m.texture < len(skin.textures) else ""
        if "圆台" in tex:
            c = (m.positions.min(0) + m.positions.max(0)) / 2
            y = ground_height(m, float(c[0]), float(c[2]))
            stage = [round(float(c[0]) + offset[0], 4), round((y if y is not None else float(m.positions.max(0)[1])) + offset[1], 4),
                     round(float(c[2]) + offset[2], 4)]
            break
    fx = []
    ecm = base.lower() + ".ecm"
    text = lib.read(ecm).decode("gbk", "replace") if ecm in lib.files else ""
    for block in re.split(r"^EventType:", text, flags=re.M)[1:]:
        path = re.search(r"FxFilePath:\s*(.+)", block)
        if not path:
            continue
        key = "gfx\\" + norm(path.group(1).strip()).lower()
        hook = re.search(r"HookOffset:\s*(.+)", block)
        scale = re.search(r"GfxScale:\s*(.+)", block)
        if key in lib.files:
            fx.append({"u": exporter.export(key), "p": value(hook.group(1)) if hook else [0, 0, 0],
                       "s": float(value(scale.group(1))) if scale else 1.0, "n": Path(key).stem})
    return {"glb": f"scene/{name}.glb", "fx": fx, "offset": offset, "stage": stage}


def export_ui(lib, wd: Path) -> dict:
    """Window textures -> ui/<name>.png; returns {original relative path: png path}."""
    out = {}
    for folder in UI_FOLDERS:
        for key in lib.under(folder.lower()):
            if not key.endswith((".tga", ".dds", ".png", ".bmp")):
                continue
            rel = norm(lib.files[key][1].path)[len("surfaces\\"):]
            png = "ui/" + re.sub(r'[\\/:*?"<>|]', "_", rel.rsplit(".", 1)[0]) + ".png"
            try:
                img = Image.open(io.BytesIO(lib.read(key)))
                img.load()
                dest = wd / png
                dest.parent.mkdir(parents=True, exist_ok=True)
                img.convert("RGBA").save(dest)
                out[rel] = png
            except Exception as ex:
                print("  ui skip", key, ex)
    return out


def palette(lib, ui: dict) -> list[dict]:
    raw = lib.read("interfaces\\collection_clothespalette.xml")
    text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8-sig", "replace")
    colors = []
    for m in re.finditer(r'<RADIO Name="Rdo_(\d+)".*?</RADIO>', text, re.S):
        block = m.group(0)
        name = re.search(r'Hint="([^"]+)"', block) or re.search(r'String="([^"]+)"', block)
        img = re.search(r'FileName="([^"]+)"', block)
        if not img:
            continue
        rel = img.group(1)
        key = ("surfaces\\" + rel).lower()
        rgb = [255, 255, 255]
        if key in lib.files:
            im = Image.open(io.BytesIO(lib.read(key))).convert("RGB")
            rgb = list(im.getpixel((im.width // 2, im.height // 2)))
        colors.append({"i": int(m.group(1)), "name": name.group(1) if name else "", "rgb": rgb})
    colors.sort(key=lambda c: c["i"])
    names = re.findall(r'String="([^"]+)"', text)
    named = [n for n in names if n not in ("Xem trước màu nhuộm", "Màu đề xuất") and not n.startswith("Ấn ")]
    for c, n in zip(colors, named):
        if not c["name"]:
            c["name"] = n
    return colors


def fashion_models(lib) -> dict:
    """Fashion model folder (the item's 'realname', lower case) -> {body type: .ski key} of the full-detail LOD."""
    out: dict = {}
    for key in lib.sorted_keys:
        if not key.endswith(".ski") or "\\players\\装备\\" not in key:
            continue
        parts = key.split("\\")
        if len(parts) != 6 or parts[3] not in ("男", "女"):
            continue
        stem = Path(parts[-1]).stem
        if LOD_RE.search(stem):
            continue
        body = next((b for b in BODIES if stem.startswith(b)), None)
        if body:
            # models2 (newer) wins over models
            if key.startswith("models2") or body not in out.get(parts[4], {}):
                out.setdefault(parts[4], {})[body] = key
    return out


def set_gender(gd: dict, s: dict) -> bool:
    """True for a female set (majority of its clothes are female items)."""
    g = [gd["items"][p]["gender"] for slot, p in s["parts"].items() if slot != "hair" and p in gd["items"]]
    return sum(g) * 2 > len(g) if g else s["name"].rstrip().endswith("nữ")


class IconAtlas:
    """Item icons from the game's icon atlases (surfaces\\iconset\\iconlist_ivtr[fm]) and collection pictures."""

    def __init__(self, lib, dest: Path):
        self.lib, self.dest = lib, dest
        dest.mkdir(parents=True, exist_ok=True)
        self.atlas = {}
        for kind in ("ivtrm", "ivtrf"):
            txt = lib.read(rf"surfaces\iconset\iconlist_{kind}.txt").decode("gbk", "replace").splitlines()
            w, h, rows, cols = (int(x) for x in txt[:4])
            names = {n.strip().lower(): i for i, n in enumerate(txt[4:]) if n.strip()}
            self.atlas[kind] = {"w": w, "h": h, "cols": cols, "names": names, "img": None}
        self.done: dict = {}

    def icon(self, name: str, female: bool) -> str | None:
        if not name:
            return None
        stem = Path(name.replace("\\", "/")).name.lower()
        for kind in (("ivtrf", "ivtrm") if female else ("ivtrm", "ivtrf")):
            a = self.atlas[kind]
            i = a["names"].get(stem)
            if i is None:
                continue
            rel = f"icons/{kind}_{i}.png"
            if rel not in self.done:
                if a["img"] is None:
                    a["img"] = Image.open(io.BytesIO(self.lib.read(rf"surfaces\iconset\iconlist_{kind}.dds"))).convert("RGBA")
                x, y = (i % a["cols"]) * a["w"], (i // a["cols"]) * a["h"]
                a["img"].crop((x, y, x + a["w"], y + a["h"])).save(self.dest / Path(rel).name)
                self.done[rel] = True
            return rel
        return None

    def picture(self, pic: str) -> str | None:
        stem = Path(pic.replace("\\", "/")).stem
        key = rf"surfaces\百宝阁\{stem}128.dds".lower()
        if key not in self.lib.files:
            return None
        rel = "icons/" + re.sub(r'[\\/:*?"<>|]', "_", stem) + ".png"
        if rel not in self.done:
            Image.open(io.BytesIO(self.lib.read(key))).convert("RGBA").save(self.dest / Path(rel).name)
            self.done[rel] = True
        return rel


def main() -> None:
    opts = dict(a[2:].split("=", 1) if "=" in a else (a[2:], "1") for a in sys.argv[1:] if a.startswith("--"))
    out = Path(opts.get("out", str(OUT / "3D")))
    wd = out / "tu_do"
    # the game's own .dds files go next to the models (tu_do/dds); the viewer samples them like the game
    os.environ["TGHM_DDS_DIR"] = str(wd / "dds")
    ski_to_glb._init_worker()
    lib = ski_to_glb._lib

    jobs: list = []
    base = build_base(lib, jobs)
    print("animations...")
    export_animations(lib, wd)
    exporter = Exporter(out, False)
    print("scenes...")
    scenes = {name: build_scene(lib, wd, exporter, name, base) for name, base in SCENES.items()}
    for name, s in scenes.items():
        print(f"  {name}: offset {s['offset']} stage {s['stage']} fx {[f['n'] for f in s['fx']]}")
    print("ui textures...")
    ui = export_ui(lib, wd)
    colors = palette(lib, ui)
    # reflection picture of the newer fashions (rewurender.hlsl: + channel.g * armorreflect)
    Image.open(io.BytesIO(lib.read(r"textures\reflect\armorreflect.bmp"))).convert("RGB").save(wd / "armorreflect.png")

    print("catalog...")
    gd = load_game_data()
    for cid, ch in CHARACTERS.items():
        preset = read_preset(lib, gd, exporter, cid, ch, base[cid], wd)
        if preset:
            preset["faceGlb"] = build_custom_face(lib, gd, cid, ch, preset, wd)
            preset.pop("_ini", None)
        base[cid]["preset"] = preset
        print(f"  {ch['label']} sample character: {preset}")
    sets = collect_sets(OUT / "manifest.csv")  # folder-named sets: only used to find the effects of a set
    set_fx = match_set_effects(lib, sets)
    exported = export_effects(lib, exporter, {k: v for k, v in set_fx.items() if k[0] == "std"})
    models = fashion_models(lib)
    icons = IconAtlas(lib, wd / "icons")

    queued: set = set()

    def glb_path(category: str, ski_key: str, cid: str, mode: str) -> str | None:
        """Queue a skinned conversion and return its path relative to the 3D folder."""
        entry = lib.files.get(ski_key)
        if not entry:
            return None
        rel = f"tu_do/sk/{cid}/{category}/" + str(Path(norm(entry[1].path)).with_suffix(".glb")).replace("\\", "/")
        if rel not in queued:
            queued.add(rel)
            jobs.append((rel, ski_key, cid, mode))
        return rel

    catalog = {"characters": base, "scenes": scenes, "palette": colors, "ui": ui, "slots": SLOT_LABEL,
               "reflect": "armorreflect.png",
               "rarity": [{"name": n, "color": c} for n, c in zip(RARITY, RARITY_COLOR)],
               "groups": {}, "sets": {}, "items": {}}
    ui_lower = {k.lower(): k for k in ui}
    pets = {}
    for ecm in sorted({s["pet"] for s in gd["sets"].values() if s["pet"].lower().endswith(".ecm")}):
        pets[ecm] = build_pet(lib, wd, ecm)
    print(f"  pets: {sum(1 for p in pets.values() if p)}/{len(pets)}")
    pics = {}  # set id -> collection picture (128x128 outfit icon)
    for il in gd["illus"].values():
        pics.setdefault(il["set"], il["pic"])
    for cid, ch in CHARACTERS.items():
        # the game fills every empty fashion slot with its default piece (cream mini skirt, top, shoes)
        base[cid]["defaults"] = {}
        for slot, folder in DEFAULT_PIECES.items():
            ski = models.get(folder, {}).get(ch["body_type"])
            if ski:
                base[cid]["defaults"][slot] = glb_path("p", ski, cid, "part")
        bon_data = lib.read(rf"{ch['folder']}\躯干\{ch['body']}.bon".lower())
        hooks = {k: [round(float(x), 4) for x in v] for k, v in hook_positions(bon_data).items()}
        base_bones = parse_bon(bon_data)
        hook_bone = {h.name: base_bones[h.bone].name for h in parse_hooks(bon_data, len(base_bones)) if h.bone >= 0}
        hook_bone.update({b.name: b.name for b in base_bones})
        female = ch["gender"] == "女"
        set_list, groups, seen = [], [], set()
        items = {s: {} for s in ["hair", *SLOT_ORDER]}

        def make_set(s: dict) -> dict | None:
            sid = f"{cid}:{s['id']}"
            parts, part_colors, part_names, top_ski = {}, {}, {}, None
            for slot, pid in s["parts"].items():
                it = gd["items"].get(pid)
                if not it or bool(it["gender"]) != female and slot != "hair":
                    continue
                if slot == "hair":
                    paths = [norm(p).lower() for h in it.get("hair", []) for p in gd["hairs"].get(h, {}).get("paths", [])]
                    # newer headwear also has a customface model (Models\customface\发型*\X\X.ecm, hair_x shader):
                    # the one the game shows; its strands take the character's hair colour (tint_x.h)
                    hd = next((k[:-4] + ".ski" for k in paths if k.endswith(".ecm") and "\\customface\\" in k
                               and k[:-4] + ".ski" in lib.files), None)
                    ski = hd or next((k for k in paths if k.endswith(".ski") and k in lib.files), None)
                    p = glb_path("3", ski, cid, "hair") if ski else None
                else:
                    # the game's window shows the standard model (Kiếm Linh has no high-model skeleton)
                    ski = models.get(it["model"].lower(), {}).get(ch["body_type"])
                    p = glb_path("p", ski, cid, "part") if ski else None
                    if ski and (slot == "top" or top_ski is None):
                        top_ski = ski
                if not p:
                    continue
                parts[slot] = p
                part_names[slot] = it["name"]
                # where the colour shows is decided by the texture's dye mask (nb_ channel map or alpha);
                # e.g. the Valentine socks carry a pink colour but their mask is empty, so they stay cream
                color = it.get("color")
                if color:
                    part_colors[slot] = color
                icon = icons.icon(it["icon"], female)
                items[slot].setdefault(p, {"glb": p, "slot": slot, "set": sid, "name": it["name"], "id": pid,
                                           "color": color, "icon": icon,
                                           **({"hairTint": True} if "/customface/" in p else {})})
            if not parts:
                return None
            fx = []
            info = classify(norm(lib.files[top_ski][1].path)) if top_ski else None
            fx_list = set_fx.get(info[:3]) if info else None
            if fx_list:
                fx = place_effects(fx_list, exported, hooks)
                for f in fx:  # effects follow the bone of their hook while the character moves
                    f["b"] = hook_bone.get(f["h"]) or hook_bone.get(HOOK_FALLBACK.get(f["h"], ""))
            pic = pics.get(s["id"])
            icon = icons.picture(pic) if pic else None
            tag = None
            if s["tag"]:  # e.g. 情人节限定标签1.tga only exists as 情人节限定标签.tga
                for name in (s["tag"], re.sub(r"\d+(\.\w+)$", r"\1", s["tag"])):
                    tag = tag or ui_lower.get(("时装套装标签\\" + name).lower())
            return {"id": sid, "gid": s["id"], "vn": s["name"], "cn": info[2] if info else "", "parts": parts,
                    "names": part_names, "colors": part_colors, "icon": icon, "fx": fx, "nghe": s["nghe"],
                    "rarity": s["rarity"], "flags": s["flags"], "tag": tag, "desc": s["desc"],
                    "source": s["source"], "action": s["action"], "pet": pets.get(s["pet"])}

        for g in sorted(gd["groups"].values(), key=lambda g: (-g["new"], g["id"])):
            ids = []
            for set_id in g["sets"]:
                s = gd["sets"].get(set_id)
                if not s or set_gender(gd, s) != female:
                    continue
                if set_id not in seen:
                    entry = make_set(s)
                    seen.add(set_id)
                    if entry:
                        set_list.append(entry)
                if any(e["gid"] == set_id for e in set_list):
                    ids.append(f"{cid}:{set_id}")
            if ids:
                groups.append({"name": g["name"], "sets": ids, "total": len(ids)})
        catalog["groups"][cid] = groups
        catalog["sets"][cid] = set_list
        catalog["items"][cid] = {s: list(v.values()) for s, v in items.items()}
        print(f"  {ch['label']}: {len(set_list)} sets in {len(groups)} groups, " +
              ", ".join(f"{SLOT_LABEL[s]} {len(v)}" for s, v in items.items()) +
              f", {sum(1 for s in set_list if s['fx'])} with effects, "
              f"{sum(1 for s in set_list if s['colors'])} with default colours")
    if "force" not in opts:  # keep models converted by an earlier run (--force-parts redoes the fashion pieces)
        redo_parts = "force-parts" in opts
        jobs = [j for j in jobs if not (out / j[0]).exists() or (redo_parts and j[3] == "part")]
    if "no-convert" in opts:
        print(f"  (skipping {len(jobs)} conversions)")
        jobs = []
    print(f"converting {len(jobs)} skinned models...", flush=True)
    workers = int(opts.get("workers", max(1, (os.cpu_count() or 2) - 1)))
    batches = [jobs[i:i + 25] for i in range(0, len(jobs), 25)]
    done, failed, empty = 0, [], set()
    with ProcessPoolExecutor(max_workers=workers, initializer=ski_to_glb._init_worker) as pool:
        futures = [pool.submit(convert_batch, b, str(out)) for b in batches]
        for n, fut in enumerate(as_completed(futures), 1):
            for dest, count, err in fut.result():
                done += 1
                if err:
                    failed.append((dest, err))
                elif not count:
                    empty.add(dest)
            if n % 20 == 0 or n == len(futures):
                print(f"  {done}/{len(jobs)}", flush=True)
    for dest, err in failed[:10]:
        print("  FAILED", dest, err)
    # drop references to models that produced nothing (e.g. heads without a separate hair mesh)
    for ch in catalog["characters"].values():
        for f in ch["faces"]:
            if f["hair"] and "tu_do/" + f["hair"] in empty:
                f["hair"] = None
    (wd / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"written {wd / 'catalog.json'} ({len(failed)} failed, {len(empty)} empty)")


if __name__ == "__main__":
    main()
