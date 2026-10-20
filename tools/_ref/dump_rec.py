"""Dump decompressed element records: strings (UTF-16 / GBK) and non-zero ints/floats with offsets."""
import pickle
import re
import struct
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tghm_paths import DATA, ELEMENT, REF  # noqa: E402

E = pickle.load(open(REF / 'elements.pkl', 'rb'))


def u16_strings(d, minlen=2):
    out = []
    i = 0
    while i + 2 <= len(d):
        if i % 2 == 0:
            j = i
            while j + 2 <= len(d) and d[j:j + 2] != b'\0\0':
                j += 2
            if j - i >= minlen * 2:
                s = d[i:j].decode('utf-16-le', 'replace')
                if sum(c.isprintable() for c in s) == len(s) and any(c.isalpha() for c in s):
                    out.append((i, s))
                    i = j
                    continue
        i += 2
    return out


def gbk_strings(d):
    out = []
    for m in re.finditer(rb'[\x21-\x7e\x81-\xfe][\x20-\x7e\x40-\xfe]{3,}', d):
        try:
            out.append((m.start(), m.group().decode('gbk')))
        except UnicodeDecodeError:
            pass
    return out


def dump(li, rid, show_zero=False):
    d = dict(E[li])[rid]
    print(f'list {li} id {rid} size {len(d)}')
    for o, s in u16_strings(d):
        print(f'   u16 @{o}: {s}')
    for o, s in gbk_strings(d):
        print(f'   gbk @{o}: {s}')
    for off in range(0, len(d) - 3, 4):
        i = struct.unpack_from('<i', d, off)[0]
        if i == 0 and not show_zero:
            continue
        f = struct.unpack_from('<f', d, off)[0]
        fs = f'{f:.4g}' if 1e-4 < abs(f) < 1e6 else ''
        print(f'   {off:5d}: {i:12d} {i & 0xffffffff:08x} {fs}')


if __name__ == '__main__':
    li = int(sys.argv[1])
    ids = [int(x) for x in sys.argv[2:]] or [r for r, _ in E[li][:3]]
    for rid in ids:
        dump(li, rid)
