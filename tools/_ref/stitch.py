"""Stitch 4 computer-use zooms (TL TR BL BR of a 1456x819 screenshot frame) into the game client image.

py stitch.py out.png tl.jpg tr.jpg bl.jpg br.jpg
Screen is 1920x1080; the game client (1900x1031) sits at screen (10, -5).
"""
import sys

from PIL import Image

out, *quads = sys.argv[1:]
full = Image.new("RGB", (1920, 1080))
for i, q in enumerate(quads):
    im = Image.open(q).convert("RGB")
    x0 = 0 if i % 2 == 0 else round(728 * 1920 / 1456)
    y0 = 0 if i < 2 else round(410 * 1080 / 819)
    w = (1920 // 2 + (0 if i % 2 == 0 else 0))
    full.paste(im, (x0, y0))
client = Image.new("RGB", (1900, 1031))
client.paste(full.crop((10, 0, 1910, 1026)), (0, 5))
client.save(out)
print(out, client.size)
