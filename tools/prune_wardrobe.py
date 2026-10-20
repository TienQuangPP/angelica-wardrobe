"""List (or delete with --delete) wardrobe models no longer referenced by tu_do/catalog.json.

py tools/prune_wardrobe.py [--out=<data>\\3D] [--delete]
Only files under tu_do/sk and tu_do/pet are considered; everything the catalog names is kept.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tghm_paths import DATA  # noqa: E402

opts = dict(a[2:].split("=", 1) if "=" in a else (a[2:], "1") for a in sys.argv[1:] if a.startswith("--"))
root = Path(opts.get("out", str(DATA / "3D")))
wd = root / "tu_do"
text = (wd / "catalog.json").read_text(encoding="utf-8")
refs = set()
for s in re.findall(r'"([^"]+\.(?:glb|json))"', text):
    s = s[len("tu_do/"):] if s.startswith("tu_do/") else s
    refs.add(s.replace("\\", "/"))
unused, size = [], 0
for folder in ("sk", "pet"):
    for p in (wd / folder).rglob("*"):
        if p.is_file() and p.relative_to(wd).as_posix() not in refs:
            unused.append(p)
            size += p.stat().st_size
print(f"{len(unused)} unreferenced files, {size / 1e6:.1f} MB")
by_folder: dict[str, int] = {}
for p in unused:
    k = "/".join(p.relative_to(wd).parts[:3])
    by_folder[k] = by_folder.get(k, 0) + 1
for k, n in sorted(by_folder.items(), key=lambda x: -x[1])[:20]:
    print(f"  {n:5d}  {k}")
if "delete" in opts:
    for p in unused:
        p.unlink()
    for d in sorted((x for f in ("sk", "pet") for x in (wd / f).rglob("*") if x.is_dir()), key=lambda x: -len(x.parts)):
        if not any(d.iterdir()):
            d.rmdir()
    print("deleted")
