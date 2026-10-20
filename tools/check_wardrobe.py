"""Audit the wardrobe catalog: missing / broken models, untextured parts, duplicates, non-Vietnamese names.

Usage: py tools/check_wardrobe.py [--out=<data>\\3D]
"""
from __future__ import annotations

import json
import re
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tghm_paths import DATA  # noqa: E402

CJK = re.compile(r"[\u3400-\u9fff]")


def glb_info(path: Path) -> dict:
    """Header check + materials without a texture + primitive count."""
    data = path.read_bytes()
    if len(data) < 20 or data[:4] != b"glTF":
        return {"error": "not a glb"}
    length = struct.unpack_from("<I", data, 8)[0]
    if length != len(data):
        return {"error": f"truncated ({len(data)} of {length} bytes)"}
    js_len = struct.unpack_from("<I", data, 12)[0]
    gltf = json.loads(data[20:20 + js_len])
    mats = gltf.get("materials", [])
    untextured = [m.get("name", "") for m in mats if "baseColorTexture" not in m.get("pbrMetallicRoughness", {})]
    prims = sum(len(m["primitives"]) for m in gltf.get("meshes", []))
    return {"prims": prims, "untextured": untextured}


def main() -> None:
    opts = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--") and "=" in a)
    root = Path(opts.get("out", str(DATA / "3D")))
    cat = json.loads((root / "tu_do" / "catalog.json").read_text(encoding="utf-8"))
    problems = defaultdict(list)
    cache: dict = {}

    def check(url: str, where: str) -> None:
        if url not in cache:
            p = root / url if url.startswith("tu_do/") else root / "tu_do" / url
            cache[url] = glb_info(p) if p.exists() else {"error": "missing file"}
        info = cache[url]
        if "error" in info:
            problems["model lỗi"].append(f"{where}: {url} ({info['error']})")
        elif not info["prims"]:
            problems["model rỗng"].append(f"{where}: {url}")
        elif info["untextured"]:
            problems["thiếu texture"].append(f"{where}: {url} {info['untextured']}")

    for cid, ch in cat["characters"].items():
        check(ch["body"], f"{cid} thân")
        for i, f in enumerate(ch["faces"], 1):
            check(f["face"], f"{cid} mặt {i}")
        for s in ch.get("styles", []):
            check(s["glb"], f"{cid} tóc {s['name']}")
    for cid, sets in cat["sets"].items():
        names = Counter(s["vn"] for s in sets)
        for n, c in names.items():
            if c > 1:
                problems["trùng tên bộ"].append(f"{cid}: {n} x{c}")
        parts = Counter(json.dumps(s["parts"], sort_keys=True) for s in sets)
        for p, c in parts.items():
            if c > 1:
                dup = [s["vn"] for s in sets if json.dumps(s["parts"], sort_keys=True) == p]
                problems["trùng bộ đồ (giống hệt)"].append(f"{cid}: {dup}")
        for s in sets:
            for slot, url in s["parts"].items():
                check(url, f"{cid} {s['vn']} [{slot}]")
            for field in ("vn", "desc", "source"):
                if CJK.search(s.get(field) or ""):
                    problems["chữ Trung"].append(f"{cid} {s['vn']} {field}: {s[field]}")
            for slot, n in s.get("names", {}).items():
                if CJK.search(n):
                    problems["chữ Trung"].append(f"{cid} {s['vn']} {slot}: {n}")
        in_groups = {i for g in cat["groups"][cid] for i in g["sets"]}
        for s in sets:
            if s["id"] not in in_groups:
                problems["bộ không thuộc nhóm"].append(f"{cid} {s['vn']}")
    for cid, slots in cat["items"].items():
        for slot, items in slots.items():
            for it in items:
                if CJK.search(it["name"]):
                    problems["chữ Trung"].append(f"{cid} {slot}: {it['name']}")
                if not it.get("icon"):
                    problems["món thiếu icon"].append(f"{cid} {slot}: {it['name']}")
    for g in [g for gs in cat["groups"].values() for g in gs]:
        if CJK.search(g["name"]):
            problems["chữ Trung"].append(f"nhóm {g['name']}")

    for cid in cat["sets"]:
        print(f"{cat['characters'][cid]['label']}: {len(cat['sets'][cid])} bộ, "
              f"nhóm {[(g['name'], g['total']) for g in cat['groups'][cid]]}")
    print(f"{len(cache)} model đã kiểm tra")
    for kind, rows in problems.items():
        print(f"\n== {kind}: {len(rows)}")
        for r in rows[:40]:
            print("  ", r)
    if not problems:
        print("không có lỗi")


if __name__ == "__main__":
    main()
