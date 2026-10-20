"""List pack files under folders (or matching a substring with --grep).

py pck_ls.py models2/players/装备/女/2023春节女装上衣 [...]
py pck_ls.py --grep 2023春节女装上衣
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from extract_fashion import Library  # noqa: E402

lib = Library()
args = sys.argv[1:]
if args and args[0] == '--grep':
    for pat in args[1:]:
        pat = pat.replace('/', '\\').lower()
        for k in lib.sorted_keys:
            if pat in k:
                print(k)
else:
    for folder in args:
        folder = folder.replace('/', '\\').lower()
        ks = lib.under(folder)
        print(folder, len(ks))
        for k in ks:
            print('   ', k)
