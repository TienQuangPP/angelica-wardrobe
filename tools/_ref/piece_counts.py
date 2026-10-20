"""Compare the piece counts shown on the game's cards with the wardrobe catalog (pieces with a model)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from game_data import load  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tghm_paths import DATA, ELEMENT, REF  # noqa: E402

gd = load()
cat = json.load(open(DATA / "3D" / "tu_do" / "catalog.json", encoding="utf-8"))
by_name = {s["vn"].replace("Bộ ", "").replace(" nữ", ""): s for s in cat["sets"]["nu"]}
# counts read on the game's cards (x/N)
game = {"Noel 2007": 4, "Noel Rực Rỡ 2008": 3, "Noel Rực Rỡ 2009": 5, "Bóng Đá": 2, "Váy Lông Vũ": 4, "Cổ Hoặc": 3,
        "Lễ phục Cổ điển": 3, "kiểu Châu Âu": 2, "Quang Vũ": 4, "Tiểu Dã Miêu": 3, "Hoa Lôi": 2, "Phổ Thông": 3,
        "Trường Kì Bào": 2, "Tân Nương": 2, "Ngày Hè Vui Vẻ": 4, "Nhạ Hỏa": 5, "Tiên Nhạc": 4, "Hoa Anh Đào": 5,
        "Thụy Thỏ Cẩm Niên": 5, "Điềm Ngôn Miêu Ngữ": 4, "Tiên Tung Điệp Vũ": 4, "Ngọc Nhị Ca": 3, "Firefox": 3,
        "Unicorn": 4, "Bạch Thỏ": 5, "Noel 2022": 4}
for name, n in game.items():
    s = by_name.get(name)
    if not s:
        print("?", name)
        continue
    rec = gd["sets"][s["gid"]]
    missing = sorted(set(rec["parts"]) - set(s["parts"]))
    flag = "" if len(s["parts"]) == n else f"  <-- thiếu {missing}"
    print(f"{name:20s} game {n}  data {len(rec['parts'])}  ours {len(s['parts'])}{flag}")
