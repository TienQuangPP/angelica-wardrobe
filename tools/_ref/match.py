"""Find where patches of the wardrobe screenshot sit in the game screenshot (offset dx, dy).

py match.py game.png ours.png name:x,y,w,h [...]   (boxes in ours.png; search +-R px)
"""
import sys

import numpy as np
from PIL import Image

R = 40
g = np.asarray(Image.open(sys.argv[1]).convert("RGB"), dtype=np.float32)
w = np.asarray(Image.open(sys.argv[2]).convert("RGB"), dtype=np.float32)
for spec in sys.argv[3:]:
    name, box = spec.split(":")
    x, y, bw, bh = map(int, box.split(","))
    patch = w[y:y + bh, x:x + bw]
    patch = patch - patch.mean()
    best = None
    for dy in range(-R, R + 1):
        for dx in range(-R, R + 1):
            yy, xx = y + dy, x + dx
            if yy < 0 or xx < 0 or yy + bh > g.shape[0] or xx + bw > g.shape[1]:
                continue
            c = g[yy:yy + bh, xx:xx + bw]
            c = c - c.mean()
            score = (patch * c).sum() / (np.sqrt((patch ** 2).sum() * (c ** 2).sum()) + 1e-6)
            if best is None or score > best[0]:
                best = (score, dx, dy)
    print(f"{name:12s} dx={best[1]:+d} dy={best[2]:+d} ncc={best[0]:.3f}")
