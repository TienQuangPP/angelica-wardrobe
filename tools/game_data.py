"""Fashion data straight from the game's elements.data (see elements_reader.py for the container format).

Lists used (0-based list index in this client's elements.data):
    82  FASHION_ESSENCE      one fashion piece: name, model folder (realname), slot, default colour (HSV range)
    193 fashion suite        a set: parts, Nghe Thuong points, rarity, tag picture, description, source, action, pet
    341 collection group     the "Thu thap" folders (one record per gender) with their set ids
    62  hair models          fashion headwear and the character creator's hairstyles (.ski paths)
    59  face shapes          the creator's .eFace shapes (face, eyes, brows, nose, mouth lines, ears)
    58  face textures        face / hair / eye textures used by the character creator
    135 third eye            forehead ornament effects (.gfx)
"""
from __future__ import annotations

import colorsys
import json
import os
import re
import struct
from pathlib import Path

from elements_reader import ELEMENTS, mppc_decompress, read_lists
from tghm_paths import DATA

CACHE = DATA / "_tools_cache" / "game_data.json"
LISTS = {"items": 82, "sets": 193, "groups": 341, "hairs": 62, "textures": 58, "third_eye": 135, "illus": 342,
         "face_shapes": 59}
SLOT_OF_EQUIP = {1: "top", 2: "wrist", 3: "bottom", 4: "shoes", 9: "hair"}
SET_SLOTS = ["hair", "top", "wrist", "bottom", "shoes"]  # order of the 5 part ids in a set record
RARITY = ["Phàm Phẩm", "Linh phẩm", "Tiên Phẩm", "Thiên Công"]  # ingame.stf 19305-19308
RARITY_COLOR = ["#00FF00", "#C700FF", "#FFCC00", "#FF1D00"]  # ingame.stf 19310-19313


def wstr(d: bytes, off: int, chars: int) -> str:
    return d[off:off + chars * 2].decode("utf-16-le", "replace").split("\x00")[0].strip()


def astr(d: bytes, off: int, size: int) -> str:
    return d[off:off + size].split(b"\x00")[0].decode("gbk", "replace").strip()


def i32(d: bytes, off: int) -> int:
    return struct.unpack_from("<i", d, off)[0]


def gbk_paths(d: bytes) -> list[str]:
    out = []
    for m in re.finditer(rb"[\x21-\x7e\x81-\xfe][\x20-\x7e\x40-\xfe]{3,}", d):
        try:
            s = m.group().decode("gbk")
        except UnicodeDecodeError:
            continue
        if re.search(r"\.(dds|tga|ski|gfx|ecm|png|bmp)$", s, re.I):
            out.append(s)
    return out


def hsv_rgb(h: float, s: float, v: float) -> list[int]:
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, max(0.0, min(1.0, s)), max(0.0, min(1.0, v)))
    # the game keeps fashion colours as 15-bit words
    return [int(round(c * 31)) * 255 // 31 for c in (r, g, b)]


def _item(rid: int, d: bytes) -> dict:
    equip = i32(d, 364)
    it = {"id": rid, "name": wstr(d, 12, 32), "model": astr(d, 76, 32), "slot": SLOT_OF_EQUIP.get(equip),
          "equip": equip, "icon": astr(d, 236, 128), "gender": i32(d, 388), "dye": i32(d, 376)}
    if equip == 9:
        it["hair"] = [h for h in (i32(d, 392), i32(d, 396)) if h > 0]
    if i32(d, 708):
        hmin, hmax, smin, smax, vmin, vmax = struct.unpack_from("<6f", d, 712)
        it["color"] = hsv_rgb((hmin + hmax) / 2, (smin + smax) / 2, (vmin + vmax) / 2)
        it["hsv"] = [round(x, 4) for x in (hmin, hmax, smin, smax, vmin, vmax)]
    return it


def _set(rid: int, d: bytes) -> dict:
    parts = struct.unpack_from("<5I", d, 196)
    return {"id": rid, "name": wstr(d, 4, 32), "icon": astr(d, 68, 128),
            "parts": {slot: pid for slot, pid in zip(SET_SLOTS, parts) if pid},
            "tag": astr(d, 224, 128), "desc": wstr(d, 352, 40), "rarity": i32(d, 416),
            # feature bits: bit i lights tag_<i+1> of collection_clothesdetail (Huyễn hóa, Bạo Nguyên, ..., Linh sủng)
            "flags": i32(d, 420),
            "source": wstr(d, 432, 32), "nghe": i32(d, 496), "action": astr(d, 500, 32),
            "pet_hook": astr(d, 532, 32), "pet": astr(d, 564, 128)}


def _group(rid: int, d: bytes) -> dict:
    ids = [x for x in struct.unpack_from(f"<{(len(d) - 212) // 4}I", d, 212) if x]
    return {"id": rid, "name": wstr(d, 4, 32), "icon": astr(d, 76, 128), "new": i32(d, 204), "order": i32(d, 208),
            "sets": ids}


def _named_paths(rid: int, d: bytes) -> dict:
    return {"id": rid, "name": wstr(d, 4, 32), "paths": gbk_paths(d)}


def _illus(rid: int, d: bytes) -> dict:
    """Collection picture of a set: surfaces\\百宝阁\\<pic stem>128.dds is the 128x128 outfit icon."""
    return {"id": rid, "name": wstr(d, 4, 32), "pic": astr(d, 196, 128), "set": i32(d, 324)}


def build() -> dict:
    data = open(ELEMENTS, "rb").read()
    lists = read_lists(data)
    out = {}
    makers = {"items": _item, "sets": _set, "groups": _group, "hairs": _named_paths, "textures": _named_paths,
              "third_eye": _named_paths, "illus": _illus, "face_shapes": _named_paths}
    for key, li in LISTS.items():
        recs = {}
        for rid, blob in lists[li].records(data):
            try:
                recs[rid] = makers[key](rid, mppc_decompress(blob))
            except Exception:  # noqa: BLE001 - a few records of unrelated lists use another layout
                continue
        out[key] = recs
    return out


def load(refresh: bool = False) -> dict:
    """Game data with integer ids (cached as JSON next to the tools)."""
    if refresh or not CACHE.exists() or CACHE.stat().st_mtime < Path(ELEMENTS).stat().st_mtime:
        gd = build()
        CACHE.parent.mkdir(exist_ok=True)
        CACHE.write_text(json.dumps(gd, ensure_ascii=False), encoding="utf-8")
    gd = json.loads(CACHE.read_text(encoding="utf-8"))
    if set(LISTS) - set(gd) or "flags" not in next(iter(gd["sets"].values())):  # older cache
        return load(refresh=True)
    return {k: {int(i): v for i, v in recs.items()} for k, recs in gd.items()}


if __name__ == "__main__":
    gd = load(refresh=True)
    print({k: len(v) for k, v in gd.items()})
    for g in gd["groups"].values():
        print(g["id"], g["name"], g["new"], g["order"], len(g["sets"]))
    s = gd["sets"][76623]
    print(s)
    for slot, pid in s["parts"].items():
        print("  ", slot, gd["items"].get(pid))
