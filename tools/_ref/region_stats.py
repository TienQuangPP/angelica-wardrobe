"""Mean / spread of colour in small regions of the character (game capture vs our render, same camera).

py region_stats.py game.png ours.png [...]
"""
import sys

import numpy as np
from PIL import Image

REGIONS = {"belly": (1000, 570, 1020, 590), "top": (987, 535, 1002, 550), "skirt": (995, 620, 1040, 640),
           "thigh": (995, 655, 1010, 665), "face": (1003, 452, 1013, 462)}


def stats(path):
    im = np.asarray(Image.open(path).convert("RGB"), float)
    out = {}
    for name, (x0, y0, x1, y1) in REGIONS.items():
        a = im[y0:y1, x0:x1].reshape(-1, 3)
        out[name] = (a.mean(0), a.mean(1).std())
    return out


ref = stats(sys.argv[1])
for p in sys.argv[1:]:
    s = stats(p)
    err = sum(np.abs(s[k][0] - ref[k][0]).mean() for k in s) / len(s)
    print(p.rsplit("\\", 1)[-1], f"err={err:.1f}",
          " ".join(f"{k}:{s[k][0].round().astype(int).tolist()}~{s[k][1]:.0f}" for k in s))
