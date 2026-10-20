"""Colour error of a wardrobe screenshot vs the game (cape, cream, skin, face): sum of channel differences.

py look_err.py ours.png [...]
"""
import sys

import numpy as np
from PIL import Image
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tghm_paths import DATA, ELEMENT, REF  # noqa: E402

game = np.asarray(Image.open(REF / "g_client.png").convert("RGB")).astype(float)


def red(img, box):
    x0, y0, x1, y1 = box
    a = img[y0:y1, x0:x1].reshape(-1, 3)
    m = (a[:, 0] > a[:, 1] + 60) & (a[:, 0] > a[:, 2] + 60)
    return np.median(a[m], 0)


def bright(img, box):
    x0, y0, x1, y1 = box
    a = img[y0:y1, x0:x1].reshape(-1, 3)
    return np.median(a[a.sum(1) > 600], 0)


def med(img, box):
    x0, y0, x1, y1 = box
    return np.median(img[y0:y1, x0:x1].reshape(-1, 3), 0)


SAMPLES = [("cape", red, (940, 480, 1100, 700), None), ("cream", bright, (940, 560, 1100, 680), None),
           ("thigh", med, (995, 740, 1010, 780), (1000, 740, 1015, 780))]
ref = {n: f(game, gb or b) for n, f, b, gb in SAMPLES}
for path in sys.argv[1:]:
    ours = np.asarray(Image.open(path).convert("RGB")).astype(float)
    vals = {n: f(ours, b) for n, f, b, _ in SAMPLES}
    err = sum(np.abs(vals[n] - ref[n]).sum() for n in ref)
    print(f"{path:28s} err {err:6.0f}  " + "  ".join(f"{n} {vals[n].astype(int).tolist()}" for n in ref))
print("game" + " " * 31 + "  ".join(f"{n} {ref[n].astype(int).tolist()}" for n in ref))
