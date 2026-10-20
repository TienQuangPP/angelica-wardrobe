"""Measure the character's colours (cape red, cream, skin) in a wardrobe screenshot vs the game's.

py look.py ours.png [game.png]
"""
import sys

import numpy as np
from PIL import Image
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tghm_paths import DATA, ELEMENT, REF  # noqa: E402


def red(img, box):
    x0, y0, x1, y1 = box
    a = img[y0:y1, x0:x1].reshape(-1, 3)
    m = (a[:, 0] > a[:, 1] + 60) & (a[:, 0] > a[:, 2] + 60)
    return np.median(a[m], 0).round() if m.any() else None


def bright(img, box):
    x0, y0, x1, y1 = box
    a = img[y0:y1, x0:x1].reshape(-1, 3)
    return np.median(a[a.sum(1) > 600], 0).round()


ours = np.asarray(Image.open(sys.argv[1]).convert("RGB")).astype(float)
game = np.asarray(Image.open(sys.argv[2] if len(sys.argv) > 2 else REF / "g_client.png").convert("RGB")).astype(float)
for name, f, box, gbox in [("cape", red, (940, 480, 1100, 700), None), ("cream", bright, (940, 560, 1100, 680), None),
                           ("skin", lambda i, b: np.median(i[b[1]:b[3], b[0]:b[2]].reshape(-1, 3), 0), (995, 740, 1010, 780),
                            (1000, 740, 1015, 780))]:
    print(f"{name:6s} game {f(game, gbox or box)} ours {f(ours, box)}")
