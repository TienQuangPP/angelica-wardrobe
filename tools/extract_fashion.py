"""Scan the game packages for fashion (时装 / thời trang) assets and extract them.

Usage:
    py tools/extract_fashion.py --dry-run           # only build manifest + catalog, print sizes
    py tools/extract_fashion.py [category ...]      # extract all or only the given categories

Output (extracted_fashion/):
    <category>/<original package path>   extracted files
    manifest.csv                         every selected file with its category/package
    missing_refs.txt                     effect references that point to files not in any package
    catalog_gshop_thoitrang.csv          fashion items sold in the item mall (gshop.data)
    catalog_icons/                       mall icons of those items as PNG
"""
from __future__ import annotations

import bisect
import csv
import io
import os
import re
import struct
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fashion_classify import is_fashion_folder  # noqa: E402
from pck_reader import Entry, Package  # noqa: E402
from tghm_paths import DATA, ELEMENT, GAME  # noqa: E402

BASE = GAME
# all extracted / generated data goes to the data folder (tghm_paths.py: TGHM_DATA / config.local.json)
OUT = DATA

CATEGORIES = {
    "1_trang_phuc": "Quần áo thời trang (上衣/下衣/鞋/护腕…), cánh trang phục nghề, ảo hóa",
    "2_vu_khi": "Vũ khí thời trang (时装武器)",
    "3_toc_dau": "Tóc / nón thời trang (时装头饰, tóc đi kèm bộ thời trang)",
    "4_dong_tac": "Động tác / biểu cảm khi mặc thời trang (时装动作, 时装舞蹈)",
    "5_hieu_ung": "Hiệu ứng (gfx) của thời trang và các texture/model nó dùng",
    "6_giao_dien": "Giao diện, icon cửa hàng thời trang (surfaces, interfaces)",
    "7_khac": "Khác: NPC mặc thời trang, mô hình rơi đồ, shader thời trang…",
}

KEYWORD_RE = re.compile(r"时装|fashion", re.I)
HAIR_EXCLUDE_RE = re.compile(r"初始|默认|初级|八军|九军")
REF_RE = re.compile(r"^\s*(\w+):\s*(.+?\.[A-Za-z0-9]{2,4})\s*$")
# Effects shared by every item (item-drop sparkle etc.), not specific to fashion.
GENERIC_GFX_PREFIXES = ("gfx\\程序联入\\",)
GSHOP_RECORD = 1464
GSHOP_FASHION_MAIN = 1  # "TT": Thời trang nam / nữ / Tọa kị / Phi hành khí / Vũ khí thời trang


def norm(path: str) -> str:
    return path.replace("/", "\\").strip("\\")


class Library:
    """All packages, addressable by normalized lower-case path."""

    def __init__(self) -> None:
        self.packages: dict[str, Package] = {}
        self.files: dict[str, tuple[str, Entry]] = {}
        for pck in sorted(ELEMENT.glob("*.pck")):
            try:
                pkg = Package(pck)
            except ValueError as ex:
                print(f"  skip {pck.name}: {ex}")
                continue
            self.packages[pck.stem] = pkg
            for e in pkg.entries:
                self.files[norm(e.path).lower()] = (pck.stem, e)
        self.sorted_keys = sorted(self.files)

    def under(self, folder_key: str) -> list[str]:
        prefix = folder_key.rstrip("\\") + "\\"
        start = bisect.bisect_left(self.sorted_keys, prefix)
        end = bisect.bisect_left(self.sorted_keys, prefix + "￿")
        return self.sorted_keys[start:end]

    def read(self, key: str) -> bytes:
        pkg, entry = self.files[key]
        return self.packages[pkg].read(entry)

    def by_package(self, name: str):
        for key, (pkg, entry) in self.files.items():
            if pkg == name:
                yield key, norm(entry.path)


class Selection:
    def __init__(self, lib: Library) -> None:
        self.lib = lib
        self.chosen: dict[str, str] = {}  # lower path -> category
        self.missing: set[str] = set()

    def add(self, key: str, category: str) -> bool:
        if key in self.chosen:
            return False
        self.chosen[key] = category
        return True

    def add_folder(self, folder_key: str, category: str) -> None:
        for key in self.lib.under(folder_key):
            self.add(key, category)

    def resolve(self, ref: str, roots: tuple[str, ...]) -> str | None:
        ref = norm(ref).lower()
        for root in roots:
            if (root + ref) in self.lib.files:
                return root + ref
        return None


def select(lib: Library) -> Selection:
    sel = Selection(lib)
    paths = {pkg: list(lib.by_package(pkg)) for pkg in lib.packages}

    # 1. Clothing: fashion folders under players\装备 (models + models2).
    for pkg in ("models", "models2"):
        folders = set()
        for key, path in paths.get(pkg, []):
            parts = path.split("\\")
            if len(parts) > 4 and parts[1].lower() == "players" and parts[2] == "装备":
                depth = 6 if parts[3] == "通用高模" else 5
                if len(parts) > depth and is_fashion_folder(parts[depth - 1]):
                    folders.add("\\".join(parts[:depth]).lower())
            elif len(parts) > 3 and parts[1].lower() == "players" and parts[2] == "装备调用翅膀":
                sel.add(key, "1_trang_phuc")
        for folder in sorted(folders):
            sel.add_folder(folder, "1_trang_phuc")

    # 2. Fashion weapons.
    sel.add_folder("models\\weapons\\人物\\时装武器", "2_vu_khi")

    # 3. Hair / headwear.
    for key, path in paths.get("facedata", []):
        if "时装头饰" in path:
            sel.add(key, "3_toc_dau")
    for key, path in paths.get("models", []):
        parts = path.split("\\")
        if len(parts) > 4 and parts[1].lower() == "customface" and parts[2].startswith("发型"):
            if not HAIR_EXCLUDE_RE.search(parts[3]):
                sel.add(key, "3_toc_dau")
        elif len(parts) > 5 and parts[1].lower() == "players" and parts[3] == "头发" and "时装" in parts[4]:
            sel.add_folder("\\".join(parts[:5]).lower(), "3_toc_dau")

    # 4-7. Remaining keyword hits, by package.
    for pkg, rows in paths.items():
        for key, path in rows:
            if not KEYWORD_RE.search(path) or key in sel.chosen:
                continue
            low = key
            if pkg in ("surfaces", "interfaces"):
                cat = "6_giao_dien"
            elif pkg == "gfx":
                cat = "5_hieu_ung"
            elif low.endswith((".stck", ".bon")) and ("\\形象\\" in path or "\\face\\" in low or "\\weapons\\" in low):
                cat = "4_dong_tac"
            elif "\\weapons\\" in low:
                cat = "2_vu_khi"
            elif "facedata" == pkg or "\\customface\\" in low:
                cat = "3_toc_dau"
            else:
                cat = "7_khac"
            sel.add(key, cat)

    add_effect_dependencies(sel)
    return sel


def text_of(data: bytes) -> str | None:
    if not data.startswith(b"MOXT") and b"Version" not in data[:64]:
        return None
    return data.decode("gbk", errors="replace")


def add_effect_dependencies(sel: Selection) -> None:
    """Follow ECM/GFX text references so fashion effects are complete."""
    queue = [k for k in sel.chosen if k.endswith((".ecm", ".gfx"))]
    seen = set()
    while queue:
        key = queue.pop()
        if key in seen:
            continue
        seen.add(key)
        text = text_of(sel.lib.read(key))
        if text is None:
            continue
        for line in text.splitlines():
            m = REF_RE.match(line)
            if not m:
                continue
            field, ref = m.group(1), m.group(2)
            ext = ref.rsplit(".", 1)[-1].lower()
            if field == "FxFilePath" or field == "GfxPath" or ext == "gfx":
                target = sel.resolve(ref, ("gfx\\", ""))
            elif field in ("TexFile", "ShaderTex"):
                target = sel.resolve(ref, ("gfx\\textures\\", "gfx\\", ""))
            elif field == "ModelPath" and key.startswith("gfx\\"):
                target = sel.resolve(ref, ("gfx\\models\\", ""))
            elif ext in ("ecm", "smd", "ski"):
                # Effect models often point at an absent Models\NPCs copy; the engine also
                # finds the file next to the ecm itself.
                target = sel.resolve(ref, ("",)) or sel.resolve(
                    ref.replace("/", "\\").rsplit("\\", 1)[-1], (key.rsplit("\\", 1)[0] + "\\",))
            else:
                continue
            if target is None:
                sel.missing.add(f"{key}\t{field}: {ref}")
                continue
            if target.startswith(GENERIC_GFX_PREFIXES):
                continue
            if sel.add(target, "5_hieu_ung") and target.endswith((".smd", ".ecm")):
                # A model used by an effect needs its whole folder (ski, bon, textures, tracks).
                sel.add_folder(target.rsplit("\\", 1)[0], "5_hieu_ung")
            if target.endswith((".gfx", ".ecm")):
                queue.append(target)


def read_gshop(lib: Library) -> list[dict]:
    data = (ELEMENT / "data" / "gshop.data").read_bytes()
    count = struct.unpack_from("<I", data, 4)[0]
    tail = data[8 + count * GSHOP_RECORD:]

    def wstr(buf: bytes, off: int, chars: int) -> str:
        raw = buf[off:off + chars * 2]
        out = []
        for i in range(0, len(raw), 2):
            c = struct.unpack_from("<H", raw, i)[0]
            if c == 0:
                break
            out.append(chr(c))
        return "".join(out).strip()

    categories: list[tuple[str, list[str]]] = []
    pos = 0
    while pos + 132 <= len(tail):
        name = wstr(tail, pos, 64)
        n = struct.unpack_from("<I", tail, pos + 128)[0]
        pos += 132
        categories.append((name, [wstr(tail, pos + i * 128, 64) for i in range(n)]))
        pos += n * 128

    items = []
    for i in range(count):
        rec = data[8 + i * GSHOP_RECORD: 8 + (i + 1) * GSHOP_RECORD]
        local_id, main, sub = struct.unpack_from("<3I", rec, 0)
        if main != GSHOP_FASHION_MAIN:
            continue
        icon = rec[12:140].split(b"\0", 1)[0].decode("gbk", errors="replace")
        item_id, num = struct.unpack_from("<2I", rec, 140)
        sub_name = categories[main][1][sub] if sub < len(categories[main][1]) else str(sub)
        items.append({
            "Danh mục": sub_name,
            "Tên": wstr(rec, 1316, 32),
            "ID vật phẩm": item_id,
            "Số lượng": num,
            "Icon": icon,
            "Mô tả": re.sub(r"\^[0-9a-fA-F]{6}", "", wstr(rec, 292, 512)).replace("\r", " ").strip(),
        })
    return items


def write_out(lib: Library, key: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    long_dest = "\\\\?\\" + str(dest.resolve())
    with open(long_dest, "wb") as fh:
        fh.write(lib.read(key))


def export_catalog(lib: Library, items: list[dict], dry_run: bool) -> None:
    with open(OUT / "catalog_gshop_thoitrang.csv", "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(items[0]) + ["PNG"])
        writer.writeheader()
        icon_dir = OUT / "catalog_icons"
        for item in items:
            key = norm(item["Icon"]).lower()
            png = ""
            if key in lib.files:
                safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", item["Tên"]) or "item"
                png = f"catalog_icons/{item['Danh mục']}/{item['ID vật phẩm']}_{safe}.png"
                if not dry_run:
                    from PIL import Image
                    target = OUT / png
                    target.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        Image.open(io.BytesIO(lib.read(key))).save(target)
                    except Exception as ex:  # unusual DDS formats
                        print(f"  icon {key}: {ex}")
                        png = ""
            writer.writerow({**item, "PNG": png})


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry_run = "--dry-run" in sys.argv
    # --out=E:\folder writes the extracted category folders elsewhere (manifest/catalog stay in OUT).
    dest_root = next((Path(a[6:]) for a in sys.argv if a.startswith("--out=")), OUT)
    wanted = set(args) or set(CATEGORIES)
    unknown = wanted - set(CATEGORIES)
    if unknown:
        sys.exit(f"unknown category: {', '.join(sorted(unknown))}; choose from {', '.join(CATEGORIES)}")

    OUT.mkdir(exist_ok=True)
    print("Loading packages...")
    lib = Library()
    print(f"  {len(lib.files)} files in {len(lib.packages)} packages")

    sel = select(lib)
    items = read_gshop(lib)
    for item in items:  # mall icons belong to the UI category
        key = norm(item["Icon"]).lower()
        if key in lib.files:
            sel.add(key, "6_giao_dien")

    stats = defaultdict(lambda: [0, 0])
    with open(OUT / "manifest.csv", "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(["category", "package", "path", "size"])
        for key in sorted(sel.chosen, key=lambda k: (sel.chosen[k], k)):
            pkg, entry = lib.files[key]
            cat = sel.chosen[key]
            writer.writerow([cat, pkg, norm(entry.path), entry.size])
            stats[cat][0] += 1
            stats[cat][1] += entry.size
    (OUT / "missing_refs.txt").write_text("\n".join(sorted(sel.missing)), encoding="utf-8")

    print(f"\n{'category':14} {'files':>7} {'size':>9}")
    for cat in CATEGORIES:
        n, size = stats[cat]
        mark = "*" if cat in wanted else " "
        print(f"{mark}{cat:13} {n:7} {size / 2**20:8.1f}M  {CATEGORIES[cat]}")
    total = sum(s for c, (_, s) in stats.items() if c in wanted)
    print(f"selected total: {total / 2**30:.2f} GB, mall fashion items: {len(items)}, "
          f"missing refs: {len(sel.missing)}")

    export_catalog(lib, items, dry_run)
    if dry_run:
        return

    done = 0
    todo = [k for k in sorted(sel.chosen) if sel.chosen[k] in wanted]
    for key in todo:
        pkg, entry = lib.files[key]
        write_out(lib, key, dest_root / sel.chosen[key] / norm(entry.path))
        done += 1
        if done % 5000 == 0:
            print(f"  {done}/{len(todo)}")
    print(f"extracted {done} files into {dest_root}")


if __name__ == "__main__":
    main()
