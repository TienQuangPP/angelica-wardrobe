"""Summarise pack folders under a prefix: file counts and extensions per folder (depth-limited).

py pck_tree.py facedata [depth]
"""
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from extract_fashion import Library  # noqa: E402

prefix = sys.argv[1].replace('/', '\\').lower().rstrip('\\') + '\\'
depth = int(sys.argv[2]) if len(sys.argv) > 2 else 3
lib = Library()
folders = defaultdict(Counter)
for k in lib.sorted_keys:
    if not k.startswith(prefix):
        continue
    parts = k.split('\\')
    folder = '\\'.join(parts[:min(len(parts) - 1, depth)])
    folders[folder][Path(k).suffix] += 1
for f in sorted(folders):
    print(f, dict(folders[f]))
