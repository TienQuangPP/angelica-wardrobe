"""Classify equipment model folders under players\\装备 as fashion or regular armor."""
from __future__ import annotations

import os
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tghm_paths import DATA  # noqa: E402

INDEX_DIR = DATA  # the _index_*.txt files of extract_fashion

# Regular armor: a short set name followed by an armor-slot word, e.g. 万象袍, 九命战铠, 北冥鞋, 15品法袍.
ARMOR_SLOTS = (
    "法袍|袍|裤|履|护腕|护手|护腿|腕甲|袖甲|腿甲|下铠|上铠|战铠|轻铠|重铠|战甲|铠甲|铠|甲|轻腕|重腕|"
    "鞋|靴|法衣|腰带|绑腿|束腕|护臂|护膝|胸甲"
)
ARMOR_RE = re.compile(rf"^(?:\d+品|\d+级)?[一-鿿]{{1,3}}(?:{ARMOR_SLOTS})$")
# Words that only appear in fashion folder names (armor names never carry a gender or skirt).
FASHION_HINT_RE = re.compile(
    r"时装|装|服|男|女|裙|上衣|下衣|裤子|鞋子|靴子|婚|礼|套|默认|旗袍|公主|郡主|飞天|绣花|\d{2}|[a-zA-Z]"
)


# Graded/class gear (15品法袍, 夜影100级上衣, 神机装备1品上衣), base clothing (默认上衣) and novice outfits.
GEAR_RE = re.compile(r"品|级|装备|重甲|轻甲|法袍|秘法|过渡|^黄金|^默认|^(?:仕女|侠客)(?:装|鞋)$")


def is_fashion_folder(name: str) -> bool:
    if "时装" in name:
        return True
    if GEAR_RE.search(name):
        return False
    if ARMOR_RE.match(name) and not FASHION_HINT_RE.search(name):
        return False
    return True


def equipment_folders(pkg: str) -> dict[str, list[tuple[str, int]]]:
    """Map 'pkg\\players\\装备\\<gender>\\<item>' -> [(path, size)].

    通用高模 (shared high-poly models) nests one level deeper: 通用高模\\<gender>\\<item>.
    """
    folders: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for line in (INDEX_DIR / f"_index_{pkg}.txt").read_text(encoding="utf-8").splitlines():
        path, size = line.rsplit("\t", 1)
        parts = path.split("\\")
        if len(parts) > 4 and parts[1] == "players" and parts[2] == "装备":
            depth = 6 if parts[3] == "通用高模" else 5
            if len(parts) > depth:
                folders["\\".join(parts[:depth])].append((path, int(size)))
    return folders


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "armor"
    for pkg in ("models", "models2"):
        folders = equipment_folders(pkg)
        fashion = {k for k in folders if is_fashion_folder(k.rsplit("\\", 1)[1])}
        print(f"== {pkg}: {len(folders)} folders -> fashion {len(fashion)}, armor {len(folders) - len(fashion)}")
        for key in sorted(folders):
            if (mode == "armor") != (key in fashion):
                print("   ", key)
