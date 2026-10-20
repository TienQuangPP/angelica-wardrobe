"""Print entries of a client .stf string table (UTF-16 text: id "string" per line) matching a regex.

py stf_grep.py interfaces\\ingame.stf "regex" [context]
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from extract_fashion import Library  # noqa: E402

key, rx = sys.argv[1].lower(), re.compile(sys.argv[2])
ctx = int(sys.argv[3]) if len(sys.argv) > 3 else 0
raw = Library().read(key)
text = raw.decode('utf-16') if raw[:2] in (b'\xff\xfe', b'\xfe\xff') else raw.decode('utf-16-le', 'replace')
entries = re.findall(r'^\s*(\d+)\s+"(.*?)"\s*$', text, re.M | re.S)
for i, (sid, s) in enumerate(entries):
    if rx.search(s) or rx.search(sid):
        for j in range(max(0, i - ctx), min(len(entries), i + ctx + 1)):
            print(('>' if j == i else ' '), entries[j][0], repr(entries[j][1][:160]))
        print('--')
