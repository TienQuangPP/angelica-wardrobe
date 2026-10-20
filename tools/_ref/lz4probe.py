"""Probe: decode elements.data as raw LZ4 block from a given offset; report how far it gets."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tghm_paths import DATA, ELEMENT, REF  # noqa: E402

d = open(ELEMENT / 'data' / 'elements.data', 'rb').read()


def lz4(src, pos, limit=1 << 26):
    out = bytearray()
    n = len(src)
    while pos < n and len(out) < limit:
        tok = src[pos]; pos += 1
        lit = tok >> 4
        if lit == 15:
            while True:
                b = src[pos]; pos += 1
                lit += b
                if b != 255:
                    break
        out += src[pos:pos + lit]; pos += lit
        if pos >= n:
            break
        off = src[pos] | src[pos + 1] << 8; pos += 2
        if off == 0 or off > len(out):
            return out, pos, f'bad offset {off} at out={len(out)}'
        ml = tok & 15
        if ml == 15:
            while True:
                b = src[pos]; pos += 1
                ml += b
                if b != 255:
                    break
        ml += 4
        start = len(out) - off
        for i in range(ml):
            out.append(out[start + i])
    return out, pos, 'end'


for off in range(int(sys.argv[1]), int(sys.argv[2])):
    out, pos, why = lz4(d, off)
    if len(out) > 2000:
        print(off, len(out), pos, why, bytes(out[:48]).hex(' '))
