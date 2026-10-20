"""Search every text-like file of the client packs for UTF-16 / UTF-8 / GBK strings.

py find_text.py "Túi Càn Khôn" ["other" ...]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from extract_fashion import Library  # noqa: E402

EXT = ('.stf', '.txt', '.ini', '.xml', '.lua', '.data', '.cfg', '.sdr', '.tab', '.htm', '.html', '.dat', '.csv')
lib = Library()
pats = []
for s in sys.argv[1:]:
    pats += [(s.encode('utf-16-le'), 'u16'), (s.encode('utf-8'), 'u8')]
hits = 0
for k in lib.sorted_keys:
    if not k.endswith(EXT):
        continue
    try:
        d = lib.read(k)
    except Exception:
        continue
    for p, enc in pats:
        i = d.find(p)
        if i < 0:
            continue
        if enc == 'u16':
            s = i
            while s >= 2 and d[s - 2:s] not in (b'\x00\x00', b'\n\x00', b'"\x00'):
                s -= 2
            e = i
            while e + 2 <= len(d) and d[e:e + 2] not in (b'\x00\x00', b'\r\x00', b'\n\x00'):
                e += 2
            text = d[s:e].decode('utf-16-le', 'replace')
        else:
            s = d.rfind(b'\n', 0, i) + 1
            e = d.find(b'\n', i)
            text = d[s:e if e > 0 else None].decode('utf-8', 'replace')
        print(k, enc, i, text[:240])
        hits += 1
        break
print('hits', hits)
