"""Build one .glb per fashion set and body type: a character wearing the whole set.

Usage:
    py tools/build_sets.py --out=<data>\\3D [--limit=N] [--workers=N] [--only=substring]

A set is every clothing folder sharing a name once the slot word is removed, e.g.
10周年女上衣 / 10周年女下衣 / 10周年女护腕 / 10周年女鞋子 -> set "10周年女".
Each part ships per body type (女通用, 妖精, 男通用, 妖兽); one character is built per body type.

Standard models: naked body + head + parts (the clothes sit on top of the body).
HD models (通用高模, 新男, 新女): the clothes already contain the skin they cover, so only the head is
added, and missing slots are filled with the HD default fashion pieces.
A matching fashion hair (时装头饰 / customface) replaces the head's default hair when one is found.
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import ski_to_glb  # noqa: E402
from extract_fashion import OUT, norm  # noqa: E402

SLOTS = {  # folder suffix -> slot
    "上衣": "top", "下衣": "bottom", "裤子": "bottom", "短裤": "bottom", "裙子": "bottom", "裙裤": "bottom",
    "护腕": "wrist", "手套": "wrist", "手链": "wrist", "鞋子": "shoes", "靴子": "shoes", "鞋": "shoes", "靴": "shoes",
}
SLOT_RE = re.compile("(" + "|".join(sorted(SLOTS, key=len, reverse=True)) + r")(?:\d*|[一-鿿]?)$")
SLOT_ORDER = ["top", "bottom", "wrist", "shoes"]
LOD_RE = re.compile(r"(二级|三级)$")
BODIES = ["女通用", "妖精", "男通用", "妖兽"]
BODY_LABEL = {"女通用": "Nữ", "妖精": "Yêu Tinh", "男通用": "Nam", "妖兽": "Yêu Thú"}
FEMALE = {"女通用", "妖精"}

STD_CHAR = {  # body type -> (body, head)
    "女通用": (r"models\players\形象\武侠女\躯干\武侠女.ski", r"models\players\形象\武侠女\头\武侠女头.ski"),
    "男通用": (r"models\players\形象\武侠男\躯干\武侠男.ski", r"models\players\形象\武侠男\头\武侠男头.ski"),
    "妖精": (r"models\players\形象\妖精\躯干\妖精1.ski", r"models\players\形象\妖精\头\妖精头.ski"),
    "妖兽": (r"models\players\形象\妖兽男\躯干\妖兽男1.ski", r"models\players\形象\妖兽男\头\妖兽男头1.ski"),
}
HD_HEAD = {
    "女通用": r"models2\players\形象\通用高模\武侠女\头简化\头简化.ski",
    "男通用": r"models2\players\形象\通用高模\武侠男\头简化\头简化.ski",
    "妖精": r"models2\players\形象\通用高模\妖精\头简化\头简化.ski",
    "妖兽": r"models2\players\形象\通用高模\妖兽男\头简化\头简化.ski",
}
# Fashion hair / face models are authored around the neck point of the face skeleton (脖子010).
# Measured by matching the same hair mesh in face space and in the world-space head models.
HEAD_OFFSET = {"女通用": (0, 1.570, 0), "妖精": (0, 1.570, 0), "男通用": (0, 1.743, 0), "妖兽": (0, 1.918, 0)}
HD_DEFAULT = {"top": "时装默认上衣", "bottom": "时装默认裤子", "wrist": "时装默认护腕", "shoes": "时装默认鞋子"}
HAIR_WORDS = re.compile(r"(头发|头饰|帽子|发型|发饰)\d*$")
NOISE = re.compile(r"[男女装服套的款系列时]|原色|变色|图鉴|\d{3,}$")


def squash(name: str) -> str:
    """Name used to match sets, hair and shop items: without gender/装/时 noise characters."""
    return NOISE.sub("", name)


def classify(path: str):
    """'models2\\players\\装备\\女\\10周年女上衣\\女通用10周年女上衣一级.ski' -> (tier, gender, set, slot, body)."""
    parts = path.split("\\")
    if len(parts) < 6 or parts[1].lower() != "players" or parts[2] != "装备":
        return None
    if parts[3] == "通用高模":
        tier, gender, folder = "hd", parts[4], parts[5] if len(parts) > 6 else None
    elif parts[3] in ("新男", "新女"):
        tier, gender, folder = "hd", parts[3][1], parts[4]
    elif parts[3] in ("男", "女"):
        tier, gender, folder = "std", parts[3], parts[4]
    else:
        return None
    stem = Path(parts[-1]).stem
    if not folder or LOD_RE.search(stem) or folder.startswith("时装默认"):
        return None
    m = SLOT_RE.search(folder)
    slot = SLOTS[m.group(1)] if m else "top"  # single-piece outfits (婚纱, 旗袍) count as the top
    set_name = folder[: m.start()] if m else folder
    body = next((b for b in BODIES if stem.startswith(b)), None)
    if body is None or not set_name:
        return None
    return tier, gender, set_name, slot, body


def collect_sets(manifest: Path) -> dict:
    sets: dict = defaultdict(lambda: defaultdict(dict))  # (tier, gender, set) -> body -> slot -> ski key
    with open(manifest, encoding="utf-8-sig") as fh:
        rows = [r for r in csv.DictReader(fh) if r["category"] == "1_trang_phuc" and r["path"].lower().endswith(".ski")]
    # models2 is newer than models: let it overwrite.
    rows.sort(key=lambda r: r["package"] == "models2")
    for r in rows:
        info = classify(norm(r["path"]))
        if info:
            tier, gender, set_name, slot, body = info
            sets[(tier, gender, set_name)][body][slot] = norm(r["path"]).lower()
    return sets


def collect_hair(manifest: Path) -> list[tuple[str, str, str]]:
    """[(squashed name, gender or '', ski key)] for fashion hair / headwear models."""
    hair = []
    with open(manifest, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            p = norm(r["path"])
            if r["category"] != "3_toc_dau" or not p.lower().endswith(".ski"):
                continue
            stem = Path(p).stem
            if LOD_RE.search(stem):
                continue
            if "\\customface\\" in p.lower():
                name = p.split("\\")[-2]
                gender = "男" if "发型男" in p else "女"
            else:
                name = stem
                gender = "男" if "男" in stem else "女" if "女" in stem else ""
            base = HAIR_WORDS.sub("", re.sub(r"\d+$", "", name)) or name
            hair.append((squash(base), gender, p.lower(), "\\customface\\" in p.lower()))
    return hair


def find_hair(set_name: str, gender: str, tier: str, hair: list) -> str | None:
    key = squash(set_name)
    if len(key) < 2:
        return None
    best, best_score = None, 0
    for name, g, ski, custom in hair:
        if g and g != gender or len(name) < 2:
            continue
        if name == key:
            score = 100
        elif len(name) >= 3 and (name in key or key in name):
            score = 50 + min(len(name), len(key))
        else:
            continue
        score += 5 if custom == (tier == "hd") else 0
        if score > best_score:
            best, best_score = ski, score
    return best


def shop_names() -> dict[tuple[str, str], str]:
    """(gender, squashed set name) -> Vietnamese shop name, from the mall icons (e.g. 盛世逢春男上衣128.dds)."""
    names = {}
    path = OUT / "catalog_gshop_thoitrang.csv"
    if not path.exists():
        return names
    genders = {"Thời trang nam": "男", "Thời trang nữ": "女"}
    with open(path, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            gender = genders.get(r["Danh mục"])
            if not gender:
                continue
            stem = re.sub(r"(128\d*|大|\d+)$", "", Path(r["Icon"].replace("\\", "/")).stem)
            stem = re.sub(r"(128\d*|大)$", "", stem)
            m = SLOT_RE.search(stem)
            base = squash(stem[: m.start()] if m else stem)
            if len(base) >= 2:
                names.setdefault((gender, base), r["Tên"].strip())
    return names


def is_default_hair(mesh, tex: str) -> bool:
    return "头发" in tex or "头发" in mesh.name or "hair" in mesh.name.lower()


def safe(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .") or "_"


def build(job: dict, out_root: str) -> tuple[str, str, str]:
    glb = ski_to_glb.GlbBuilder()
    warnings: list[str] = []
    materials: dict = {}
    hair = job["hair"]
    drop_hair = (lambda mesh, tex: not is_default_hair(mesh, tex)) if hair else None
    try:
        for label, key, keep in job["pieces"]:
            if label == "head":
                keep = drop_hair
            if key not in ski_to_glb._lib.files:
                warnings.append(f"missing {label}: {key}")
                continue
            ski_to_glb.add_skin(glb, key, label, materials, warnings, keep)
        if hair:
            ski_to_glb.add_skin(glb, hair, "hair", materials, warnings, offset=HEAD_OFFSET[job["body"]])
        data = glb.finish(extras={"set": job["set"], "body": job["body"], "parts": job["parts"], "hair": hair or ""})
        dest = Path(out_root) / job["dest"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open("\\\\?\\" + str(dest.resolve()), "wb") as fh:
            fh.write(data)
        return job["dest"], "ok", "; ".join(warnings)
    except Exception as ex:
        return job["dest"], "error", f"{type(ex).__name__}: {ex}"


def work(batch: list[dict], out_root: str) -> list:
    return [build(job, out_root) for job in batch]


def make_jobs(limit: int, only: str | None) -> list[dict]:
    manifest = OUT / "manifest.csv"
    sets = collect_sets(manifest)
    hair = collect_hair(manifest)
    vn = shop_names()
    jobs = []
    for (tier, gender, set_name), bodies in sorted(sets.items()):
        if only and not any(o in set_name for o in only.split("|")):
            continue
        slots_in_set = set().union(*(b.keys() for b in bodies.values()))
        for body, parts in sorted(bodies.items()):
            if (body in FEMALE) != (gender == "女"):
                continue
            pieces = []
            if tier == "std":
                body_ski, head = STD_CHAR[body]
                pieces += [("body", body_ski.lower(), None), ("head", head.lower(), None)]
            else:
                pieces.append(("head", HD_HEAD[body].lower(), None))
            for slot in SLOT_ORDER:
                if slot in parts:
                    pieces.append((slot, parts[slot], None))
                elif tier == "hd" and slot not in slots_in_set:
                    # The default piece supplies the skin of that body area.
                    folder = HD_DEFAULT[slot]
                    pieces.append((f"{slot}(mặc định)",
                                   rf"models2\players\装备\新{gender}\{folder}\{body}{folder}一级.ski".lower(), None))
            vn_name = vn.get((gender, squash(set_name)), "")
            title = f"{vn_name} [{set_name}]" if vn_name else set_name
            tier_label = " (HD)" if tier == "hd" else ""
            group = f"{'Nữ' if gender == '女' else 'Nam'}{tier_label}"
            dest = f"0_bo_thoi_trang/{safe(group)}/{safe(title)}/{safe(set_name)}_{BODY_LABEL[body]}.glb"
            jobs.append({
                "set": set_name, "vn": vn_name, "tier": tier, "gender": gender, "body": body, "group": group,
                "title": title, "pieces": pieces, "parts": {s: parts[s] for s in parts},
                "hair": find_hair(set_name, gender, tier, hair), "dest": dest,
            })
    return jobs[:limit] if limit else jobs


def main() -> None:
    opts = dict(a[2:].split("=", 1) if "=" in a else (a[2:], "1") for a in sys.argv[1:] if a.startswith("--"))
    out_root = Path(opts.get("out", str(OUT / "3D")))
    workers = int(opts.get("workers", max(1, (os.cpu_count() or 2) - 1)))
    jobs = make_jobs(int(opts.get("limit", 0)), opts.get("only"))
    previous: list = []
    if "retry-failed" in opts:
        # Rebuild only the characters that failed last time and keep the other report rows.
        with open(out_root / "sets_report.csv", encoding="utf-8-sig") as fh:
            rows = list(csv.reader(fh))[1:]
        failed = {r[0] for r in rows if r[1] != "ok"}
        previous = [(r[0], r[1], r[2]) for r in rows if r[1] == "ok"]
        jobs_all = jobs
        jobs = [j for j in jobs if j["dest"] in failed]
    with_hair = sum(1 for j in jobs if j["hair"])
    with_vn = len({j["set"] for j in jobs if j["vn"]})
    print(f"{len(jobs)} characters from {len({(j['tier'], j['gender'], j['set']) for j in jobs})} sets "
          f"({with_hair} with fashion hair, {with_vn} sets named from the shop) -> {out_root}", flush=True)

    batches = [jobs[i:i + 10] for i in range(0, len(jobs), 10)]
    report = []
    start = time.time()
    with ProcessPoolExecutor(max_workers=workers, initializer=ski_to_glb._init_worker) as pool:
        futures = [pool.submit(work, b, str(out_root)) for b in batches]
        for n, fut in enumerate(as_completed(futures), 1):
            report += fut.result()
            if n % 20 == 0 or n == len(futures):
                print(f"  {len(report)}/{len(jobs)}  {time.time() - start:.0f}s", flush=True)

    if "retry-failed" in opts:
        report += previous
        jobs = jobs_all
    meta = {j["dest"]: j for j in jobs}
    report = [r for r in report if r[0] in meta]
    out_root.mkdir(parents=True, exist_ok=True)
    with open(out_root / "sets_report.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["file", "status", "note", "set", "vn_name", "body", "parts", "hair"])
        for dest, status, note in sorted(report):
            j = meta[dest]
            w.writerow([dest, status, note, j["set"], j["vn"], j["body"],
                        " + ".join(f"{k}" for k in j["parts"]), j["hair"] or ""])
    built = {r[0] for r in report if r[1] == "ok"}
    (out_root / "sets.json").write_text(json.dumps(
        [{"p": j["dest"], "n": f"{j['title']} — {BODY_LABEL[j['body']]}", "g": "Bộ: " + j["group"]}
         for j in jobs if j["dest"] in built],
        ensure_ascii=False), encoding="utf-8")
    ok = sum(1 for r in report if r[1] == "ok")
    print(f"built {ok}/{len(report)} characters; report: {out_root / 'sets_report.csv'}")


if __name__ == "__main__":
    main()
