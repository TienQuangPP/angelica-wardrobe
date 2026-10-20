"""Mean |Laplacian| (high-frequency detail) of the same regions in the game capture and our renders.

py sharp.py game.png ours1.png [ours2.png ...]
"""
import sys

import numpy as np
from PIL import Image

BOXES = {"top": (960, 470, 1050, 560), "skirt": (950, 600, 1060, 660), "legs": (970, 700, 1060, 860)}


def sharp(path, box):
    a = np.asarray(Image.open(path).convert("L").crop(box), float)
    lap = np.abs(4 * a[1:-1, 1:-1] - a[:-2, 1:-1] - a[2:, 1:-1] - a[1:-1, :-2] - a[1:-1, 2:])
    return lap.mean()


for name, box in BOXES.items():
    print(f"{name:6s}", "  ".join(f"{p.rsplit(chr(92), 1)[-1]}={sharp(p, box):.2f}" for p in sys.argv[1:]))
