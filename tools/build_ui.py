"""Export the game's own UI dialogs (interfaces\\*.xml, Angelica AUI) for the wardrobe page.

Usage: py tools/build_ui.py --out=<data>\\3D

Writes <out>/tu_do/ui2/layout.json with every control of the "Thu thập" (collection) dialogs - type,
position, size, text style and images - and converts the images they use to <out>/tu_do/ui2/img/*.png.
The page (aui.js) rebuilds the dialogs from this file so they match the game pixel for pixel.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from extract_fashion import OUT, Library, norm  # noqa: E402

DIALOGS = [
    "collectionmain", "collection_bg", "collection_clothesmain", "collection_clothessub", "collection_ctrl_clothes0",
    "collection_clothesdetail", "collection_clothespalette", "collection_totalbutton", "collection_bgbtn",
    "collection_clothessuball", "collection_search",
]
IMAGE_ATTRS = ("TitleImage", "ButtonFoldImg", "ButtonUnfoldImg")
# images the game's code picks at run time (not named in the XML): the rarity plate behind "Độ hiếm"
EXTRA_IMAGES = [rf"version02\系统\时装图鉴\图鉴标签\魅力值底板{c}.tga" for c in ("绿", "紫", "黄", "红")]
# strings of interfaces\ingame.stf the window uses (default source lines, rarity names, plate text)
STRINGS = [19290, 19291, 19305, 19306, 19307, 19308, 19331, 19341]


def read_stf(lib: Library, name: str) -> dict:
    raw = lib.read(f"interfaces\\{name}")
    text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-16-le", "replace")
    return {int(i): s for i, s in re.findall(r'^\s*(\d+)\s+"(.*?)"\s*$', text, re.M | re.S)}


def read_xml(lib: Library, name: str) -> ET.Element:
    raw = lib.read(f"interfaces\\{name}.xml")
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = raw.decode("utf-16")
    else:
        text = raw.decode("utf-8-sig", "replace")
    return ET.fromstring(text.lstrip("\ufeff"))


def color(value: str | None):
    if not value:
        return None
    parts = [int(x) for x in value.split(",")]
    return parts + [255] * (4 - len(parts))


class Images:
    def __init__(self, lib: Library, dest: Path):
        self.lib, self.dest, self.done = lib, dest, {}

    def add(self, rel: str | None):
        if not rel:
            return None
        rel = norm(rel)
        if rel in self.done:
            return rel if self.done[rel] else None
        key = ("surfaces\\" + rel).lower()
        info = None
        if key in self.lib.files:
            try:
                img = Image.open(io.BytesIO(self.lib.read(key)))
                img.load()
                name = hashlib.md5(rel.encode("utf-8")).hexdigest()[:12] + ".png"
                self.dest.mkdir(parents=True, exist_ok=True)
                img.convert("RGBA").save(self.dest / name)
                info = {"u": "img/" + name, "w": img.width, "h": img.height}
            except Exception as ex:
                print("  image skip", rel, ex)
        self.done[rel] = info
        return rel if info else None


def control(el: ET.Element, images: Images) -> dict:
    a = el.attrib
    c = {"type": el.tag, "name": a.get("Name", ""), "x": int(a.get("x", 0)), "y": int(a.get("y", 0)),
         "w": int(a.get("Width", 0) or 0), "h": int(a.get("Height", 0) or 0)}
    for k in ("Align", "TextOffsetX", "TextOffsetY", "ReadOnly", "GroupID", "ButtonID", "DialogFile", "FolderID",
              "Hint", "MaxLen", "Command", "RenderTop"):
        if k in a:
            c[k] = a[k]
    text = el.find("Text")
    if text is not None:
        t = text.attrib
        c["text"] = {"s": t.get("String", ""), "size": float(t.get("FontSize", 10) or 10),
                     "bold": t.get("Bold") == "true", "color": color(t.get("Color")),
                     "outline": int(t.get("Outline", 0) or 0), "oc": color(t.get("OutlineColor")),
                     "shadow": int(t.get("Shadow", 0) or 0)}
    imgs = {}
    res = el.find("Resource")
    if res is not None:
        for r in res:
            path = images.add(r.get("FileName"))
            if path:
                imgs[r.tag] = path
    for child in el:
        for k in IMAGE_ATTRS:
            path = images.add(child.get(k))
            if path:
                imgs[k] = path
        if child.tag in ("TitleInfo", "ButtonInfo"):
            for k in ("TitleWidth", "TitleHeight", "ButtonWidth", "ButtonHeight"):
                if child.get(k):
                    c[k] = int(child.get(k))
    if imgs:
        c["img"] = imgs
    return c


def main() -> None:
    opts = dict(a[2:].split("=", 1) if "=" in a else (a[2:], "1") for a in sys.argv[1:] if a.startswith("--"))
    out = Path(opts.get("out", str(OUT / "3D"))) / "tu_do" / "ui2"
    lib = Library()
    images = Images(lib, out / "img")
    layout = {"dialogs": {}, "images": {}}
    for name in DIALOGS:
        root = read_xml(lib, name)
        frame = None
        res = root.find("Resource")
        if res is not None and res.find("FrameImage") is not None:
            frame = images.add(res.find("FrameImage").get("FileName"))
        layout["dialogs"][name] = {
            "name": root.get("Name"), "w": int(root.get("Width", 0)), "h": int(root.get("Height", 0)), "frame": frame,
            "controls": [control(el, images) for el in root if el.tag != "Resource"],
        }
        print(f"  {name}: {len(layout['dialogs'][name]['controls'])} controls")
    layout["extra"] = [p for p in map(images.add, EXTRA_IMAGES) if p]
    stf = read_stf(lib, "ingame.stf")
    layout["strings"] = {i: stf[i] for i in STRINGS if i in stf}
    layout["images"] = {k: v for k, v in images.done.items() if v}
    out.mkdir(parents=True, exist_ok=True)
    (out / "layout.json").write_text(json.dumps(layout, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(layout['images'])} images -> {out}")


if __name__ == "__main__":
    main()
