"""Match fashion effects (.gfx) to fashion sets, export them for the 3D viewer.

Usage:
    py tools/build_fx.py --out=<data>\\3D [--dry]

The mapping "which outfit plays which effect on which hook" lives in the encrypted elements.data,
so it is approximated here:
  * effect roots = fashion .gfx files not nested inside another effect, minus weapon/skill effects;
  * an effect belongs to a set when its name prefix matches the set name (fuzzy, gender aware);
  * the hook comes from the name suffix (左脚 -> HH_左脚, 鞋 -> both feet, 手环 -> both hands...),
    positions taken from the character skeleton (.bon) in bind pose.

Writes <out>/fx/<id>.json (effect + nested effects), fx/tex/*.png, fx/models/*.glb and adds an
"fx" list to every character entry of <out>/sets.json.
"""
from __future__ import annotations

import difflib
import hashlib
import io
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import ski_to_glb  # noqa: E402
from bon_reader import hook_positions  # noqa: E402
from build_sets import BODY_LABEL, FEMALE, collect_sets, squash  # noqa: E402
from extract_fashion import OUT, norm  # noqa: E402
from gfx_reader import parse_gfx  # noqa: E402

WEAPON_RE = re.compile(
    r"单手|双手|弓|弩|法球|拳套|匕首|镰刀|胧刀|短杖|长杖|长兵|短兵|法宝|棍|锤|枪|剑|刀|火炮|琴|鞭|扇|钉耙|"
    r"地面|爆|轨迹|吟唱|技能|发射|打出|施放|刀光|拖尾|蓄力|攻击|展示|旋风|踢腿|撕咬|武器|舞蹈|飞行|坐骑")
# name suffix -> hooks (first match wins)
HOOK_RULES = [
    ("左脚", ["HH_左脚"]), ("右脚", ["HH_右脚"]), ("左肩", ["HH_zuojian"]), ("右肩", ["HH_youjian"]),
    ("左手", ["Bip01 L Hand"]), ("右手", ["Bip01 R Hand"]), ("左腰", ["HH_zuoyao"]), ("腰左", ["HH_zuoyao"]),
    ("右腰", ["HH_youyao"]), ("腰右", ["HH_youyao"]), ("左膝", ["HH_左膝"]), ("右膝", ["HH_右膝"]),
    ("手臂", ["HH_左大臂", "HH_右大臂"]), ("肩", ["HH_zuojian", "HH_youjian"]),
    ("手", ["Bip01 L Hand", "Bip01 R Hand"]), ("护腕", ["Bip01 L Hand", "Bip01 R Hand"]),
    ("小腿", ["HH_左膝", "HH_右膝"]), ("膝", ["HH_左膝", "HH_右膝"]),
    ("鞋", ["HH_左脚", "HH_右脚"]), ("靴", ["HH_左脚", "HH_右脚"]), ("脚", ["HH_左脚", "HH_右脚"]),
    ("翅膀", ["HH_chibang"]), ("背", ["HH_chibang"]), ("脖子", ["Bip01 Neck"]), ("项链", ["Bip01 Neck"]),
    ("头", ["Bip01 Head"]), ("帽", ["Bip01 Head"]), ("胸", ["Bip01 Spine2"]), ("腰", ["Bip01 Pelvis"]),
    ("裙", ["Bip01 Pelvis"]), ("下身", ["Bip01 Pelvis"]), ("下衣", ["Bip01 Pelvis"]), ("裤", ["Bip01 Pelvis"]),
]
# Skeletons without a given hook (e.g. 妖兽男 has no HH_左大臂) use the nearest bone instead.
HOOK_FALLBACK = {
    "HH_左大臂": "Bip01 L UpperArm", "HH_右大臂": "Bip01 R UpperArm", "HH_zuojian": "Bip01 L Clavicle",
    "HH_youjian": "Bip01 R Clavicle", "HH_左脚": "Bip01 L Foot", "HH_右脚": "Bip01 R Foot",
    "HH_左膝": "Bip01 L Calf", "HH_右膝": "Bip01 R Calf", "HH_chibang": "Bip01 Spine2",
    "HH_zuoyao": "Bip01 Pelvis", "HH_youyao": "Bip01 Pelvis",
}
SKELETON = {
    ("std", "女通用"): r"models\players\形象\武侠女\躯干\武侠女.bon",
    ("std", "妖精"): r"models\players\形象\妖精\躯干\妖精.bon",
    ("std", "男通用"): r"models\players\形象\武侠男\躯干\武侠男.bon",
    ("std", "妖兽"): r"models\players\形象\妖兽男\躯干\妖兽男.bon",
    ("hd", "女通用"): r"models2\players\形象\通用高模\武侠女\躯干\武侠女.bon",
    ("hd", "妖精"): r"models2\players\形象\通用高模\妖精\躯干\妖精.bon",
    ("hd", "男通用"): r"models2\players\形象\通用高模\武侠男\躯干\武侠男.bon",
    ("hd", "妖兽"): r"models2\players\形象\通用高模\妖兽男\躯干\妖兽男.bon",
}
MAX_FX_PER_CHARACTER = 16


def fx_id(key: str) -> str:
    return hashlib.md5(key.encode("utf-8")).hexdigest()[:12]


def gfx_prefix(stem: str) -> str:
    stem = re.sub(r"(效果|特效)\d*$", "", stem)
    return stem.split("_", 1)[0] if "_" in stem else stem


def hooks_for(stem: str, aabb) -> list[str]:
    suffix = stem.split("_", 1)[1] if "_" in stem else stem
    for word, hooks in HOOK_RULES:
        if word in suffix:
            return hooks
    # No body part named: effects drawn around the whole body are authored from the feet (origin),
    # small ones are centred on the chest.
    if aabb and (aabb[1][1] - aabb[0][1]) > 0.6:
        return ["origin"]
    return ["Bip01 Spine1"]


def year(name: str) -> str:
    """'2015冰淇淋' / '15圣诞' -> '15'; '' when the name carries no year."""
    m = re.match(r"(?:20)?(\d{2})(?!\d)", name)
    return m.group(1) if m else ""


def similar(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if year(a) and year(b) and year(a) != year(b):
        return 0.0  # 13圣诞 must not take the effects of 15圣诞
    a2, b2 = re.sub(r"^(?:20)?\d{2}", "", a), re.sub(r"^(?:20)?\d{2}", "", b)
    if year(a) != year(b) and len(a2) <= 3:
        return 0.0  # a bare theme word (圣诞) is not enough without the same year
    a, b = a2 or a, b2 or b
    if a == b:
        return 1.0
    if len(a) >= 3 and len(b) >= 3 and (a in b or b in a):
        return 0.9
    return difflib.SequenceMatcher(None, a, b).ratio()


class Exporter:
    def __init__(self, out: Path, dry: bool):
        self.lib = ski_to_glb._lib
        self.out = out
        self.dry = dry
        self.tex_done: dict[str, str | None] = {}
        self.model_done: dict[str, str | None] = {}
        self.missing: set[str] = set()

    def texture(self, name: str) -> str | None:
        if not name:
            return None
        key = "gfx\\textures\\" + norm(name).lower()
        if key not in self.lib.files:
            alt = norm(name).lower()
            key = alt if alt in self.lib.files else key
        if key in self.tex_done:
            return self.tex_done[key]
        url = None
        if key in self.lib.files:
            url = f"tex/{fx_id(key)}.png"
            if not self.dry:
                from PIL import Image
                try:
                    img = Image.open(io.BytesIO(self.lib.read(key)))
                    img.load()
                    img = img.convert("RGBA")
                    if max(img.size) > 512:
                        img.thumbnail((512, 512))
                    dest = self.out / "fx" / url
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    img.save(dest, "PNG", compress_level=6)
                except Exception:
                    url = None
        else:
            self.missing.add(key)
        self.tex_done[key] = url
        return url

    def model(self, smd: str) -> str | None:
        """gfx model element: convert the skins next to the .SMD into one glb."""
        folder = ("gfx\\models\\" + norm(smd).lower()).rsplit("\\", 1)[0]
        if folder in self.model_done:
            return self.model_done[folder]
        skis = [k for k in self.lib.under(folder) if k.endswith(".ski") and k.count("\\") == folder.count("\\") + 1]
        url = None
        if skis:
            url = f"models/{fx_id(folder)}.glb"
            if not self.dry:
                glb = ski_to_glb.GlbBuilder()
                mats, warns = {}, []
                n = sum(ski_to_glb.add_skin(glb, k, Path(k).stem, mats, warns) for k in skis)
                if n:
                    dest = self.out / "fx" / url
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(glb.finish())
                else:
                    url = None
        self.model_done[folder] = url
        return url

    def export(self, root_key: str) -> str:
        """Write fx/<id>.json holding the root effect and every nested effect it uses."""
        defs: dict[str, dict] = {}

        def visit(key: str, depth: int) -> str | None:
            if key in defs or depth > 6:
                return key if key in defs else None
            if key not in self.lib.files:
                self.missing.add(key)
                return None
            g = parse_gfx(self.lib.read(key).decode("gbk", "replace"))
            defs[key] = g
            for el in g["elements"]:
                el["tex"] = self.texture(el.get("tex", ""))
                props = el["props"]
                if el["t"] == 200 and props.get("GfxPath"):
                    child = "gfx\\" + norm(str(props["GfxPath"])).lower()
                    el["gfx"] = visit(child, depth + 1)
                elif el["t"] == 160 and props.get("ModelPath"):
                    el["model"] = self.model(str(props["ModelPath"]))
            return key

        visit(root_key, 0)
        fid = fx_id(root_key)
        if not self.dry:
            dest = self.out / "fx" / f"{fid}.json"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps({"root": root_key, "defs": defs}, ensure_ascii=False,
                                       separators=(",", ":")), encoding="utf-8")
        return f"fx/{fid}.json"


def place_effects(fx_list, exported: dict, hooks: dict) -> list[dict]:
    """[(gfx key, stem)] -> viewer entries {u, p, n, h} positioned on the given skeleton hooks."""
    items = []
    stems = [stem for _, stem in fx_list]
    for k, stem in fx_list:
        url, hook_names = exported[k]
        if len(hook_names) == 2:
            # "X" next to "X_右脚" is the left-side half of a pair (and vice versa).
            sides = [s for s in stems if s != stem and s.startswith(stem)]
            if any("右" in s for s in sides):
                hook_names = hook_names[:1]
            elif any("左" in s for s in sides):
                hook_names = hook_names[1:]
        for h in hook_names:
            if h == "origin":
                pos = [0.0, 0.0, 0.0]
            else:
                p = hooks.get(h)
                if p is None:
                    p = hooks.get(HOOK_FALLBACK.get(h, ""))
                if p is None:
                    continue
                pos = [round(float(x), 4) for x in p]
            items.append({"u": url, "p": pos, "n": stem, "h": h})
    return items[:MAX_FX_PER_CHARACTER]


def match_set_effects(lib, sets) -> dict:
    """{(tier, gender, set name): [(gfx key, stem)]} for every set whose name matches effect files."""
    fashion = [k for k in lib.files if k.startswith("gfx\\人物\\") and k.endswith(".gfx") and "时装" in k]
    children = set()
    for k in fashion:
        for m in re.finditer(r"GfxPath:\s*(.+?\.gfx)", lib.read(k).decode("gbk", "replace"), re.I):
            children.add("gfx\\" + norm(m.group(1)).lower())
    roots = [k for k in fashion if k not in children and not WEAPON_RE.search(Path(k).stem)]
    print(f"{len(fashion)} fashion effects, {len(roots)} candidate roots after removing nested/weapon/skill ones")
    root_info = []
    for k in roots:
        stem = Path(k).stem
        male, female = "男" in stem, "女" in stem
        gender = "男" if male and not female else "女" if female and not male else ""
        root_info.append((k, stem, squash(gfx_prefix(stem)), gender))
    set_fx: dict = {}
    for (tier, gender, name) in sets:
        key = squash(name)
        if len(key) < 2:
            continue
        best = [(similar(key, sq), k, stem) for k, stem, sq, g in root_info if not g or g == gender]
        best = [b for b in best if b[0] >= 0.75]
        if best:
            top = max(s for s, _, _ in best)
            set_fx[(tier, gender, name)] = [(k, stem) for s, k, stem in best if s >= top - 0.05]
    return set_fx


def export_effects(lib, exporter: "Exporter", set_fx: dict) -> dict:
    exported: dict[str, tuple[str, list]] = {}
    for fx_list in set_fx.values():
        for k, stem in fx_list:
            if k not in exported:
                aabb = parse_gfx(lib.read(k).decode("gbk", "replace"))["aabb"]
                exported[k] = (exporter.export(k), hooks_for(stem, aabb))
    return exported


def main() -> None:
    opts = dict(a[2:].split("=", 1) if "=" in a else (a[2:], "1") for a in sys.argv[1:] if a.startswith("--"))
    out = Path(opts.get("out", str(OUT / "3D")))
    dry = "dry" in opts
    ski_to_glb._init_worker()
    lib = ski_to_glb._lib
    sets = collect_sets(OUT / "manifest.csv")
    set_fx = match_set_effects(lib, sets)
    print(f"sets with effects: {len(set_fx)} / {len(sets)}")
    exporter = Exporter(out, dry)
    skeletons = {tb: hook_positions(lib.read(path.lower())) for tb, path in SKELETON.items()
                 if path.lower() in lib.files}
    exported = export_effects(lib, exporter, set_fx)
    print(f"exported {len(exported)} effects, {sum(1 for v in exporter.tex_done.values() if v)} textures, "
          f"{sum(1 for v in exporter.model_done.values() if v)} effect models, {len(exporter.missing)} missing refs")
    _write_outputs(out, dry, set_fx, exported, skeletons)


def _write_outputs(out: Path, dry: bool, set_fx: dict, exported: dict, skeletons: dict) -> None:
    if dry:
        for s, fx_list in list(set_fx.items())[:40]:
            print(" ", s[2], s[1], s[0], "->", [(stem, exported[k][1]) for k, stem in fx_list][:5])
        return
    sets_json = out / "sets.json"
    entries = json.loads(sets_json.read_text(encoding="utf-8"))
    dest_meta = {r["file"]: r for r in csv_rows(out / "sets_report.csv")}
    count = 0
    for e in entries:
        r = dest_meta.get(e["p"])
        if not r:
            continue
        tier = "hd" if "(HD)" in e["g"] else "std"
        gender = "女" if r["body"] in FEMALE else "男"
        fx_list = set_fx.get((tier, gender, r["set"]))
        e.pop("fx", None)
        if not fx_list:
            continue
        hooks = skeletons.get((tier, r["body"])) or skeletons.get(("std", r["body"]), {})
        e["fx"] = place_effects(fx_list, exported, hooks)
        count += 1
    sets_json.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    (out / "fx_report.txt").write_text(
        "\n".join(f"{s[2]} [{s[1]} {s[0]}]: " + ", ".join(stem for _, stem in v) for s, v in sorted(set_fx.items())),
        encoding="utf-8")
    print(f"{count} characters now carry effects; details in {out / 'fx_report.txt'}")


def csv_rows(path: Path):
    import csv
    with open(path, encoding="utf-8-sig") as fh:
        yield from csv.DictReader(fh)


if __name__ == "__main__":
    main()
