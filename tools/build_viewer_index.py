"""Write index.json for the 3D viewer: every .glb below the given folder.

Full-set characters (0_bo_thoi_trang) take their display name and group from sets.json
written by build_sets.py, and are listed first.

Usage: py tools/build_viewer_index.py <data>\\3D
"""
import json
import sys
from pathlib import Path

GROUPS = {
    "1_trang_phuc": "Từng món quần áo",
    "2_vu_khi": "Vũ khí thời trang",
    "3_toc_dau": "Tóc / nón",
    "5_hieu_ung": "Mô hình trong hiệu ứng",
    "7_khac": "Khác",
}

root = Path(sys.argv[1])
sets = {}
if (root / "sets.json").exists():
    sets = {s["p"]: s for s in json.loads((root / "sets.json").read_text(encoding="utf-8"))}

items = []
for glb in sorted(root.rglob("*.glb")):
    rel = glb.relative_to(root).as_posix()
    top = rel.split("/", 1)[0]
    if rel in sets:
        items.append({"p": rel, "n": sets[rel]["n"], "g": sets[rel]["g"], "fx": sets[rel].get("fx")})
    elif top != "0_bo_thoi_trang":
        items.append({"p": rel, "g": GROUPS.get(top, top)})
items.sort(key=lambda i: (not i["g"].startswith("Bộ"), i["g"], i.get("n") or i["p"]))
for i in items:
    if not i.get("fx"):
        i.pop("fx", None)
(root / "index.json").write_text(json.dumps({"items": items}, ensure_ascii=False, separators=(",", ":")),
                                 encoding="utf-8")
print(f"{len(items)} models indexed ({sum(1 for i in items if i['p'] in sets)} full sets) -> {root / 'index.json'}")
