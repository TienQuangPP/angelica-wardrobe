"""Print a range of ids of a .stf string table, sorted by id.

py stf_range.py interfaces\\ingame.stf 19280 19330
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from extract_fashion import Library  # noqa: E402

raw = Library().read(sys.argv[1].lower())
text = raw.decode('utf-16') if raw[:2] in (b'\xff\xfe', b'\xfe\xff') else raw.decode('utf-16-le', 'replace')
entries = {int(i): s for i, s in re.findall(r'^\s*(\d+)\s+"(.*?)"\s*$', text, re.M | re.S)}
lo, hi = int(sys.argv[2]), int(sys.argv[3])
for i in sorted(k for k in entries if lo <= k <= hi):
    print(i, repr(entries[i][:200]))
