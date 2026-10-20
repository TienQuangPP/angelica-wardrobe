"""Print the elements of an exported effect JSON (fx/<hash>.json): type, texture, size, scale, blend."""
import json
import sys

d = json.load(open(sys.argv[1], encoding='utf-8'))
for path, g in d['defs'].items():
    print('==', path, {k: v for k, v in g.items() if not isinstance(v, (list, dict))})
    for e in g.get('elements', g.get('els', [])):
        short = {k: (v if not isinstance(v, (list, dict)) else (str(v)[:100])) for k, v in e.items()}
        print('  ', short)
