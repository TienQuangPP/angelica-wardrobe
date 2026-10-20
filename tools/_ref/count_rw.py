"""Count fashion textures of the rewurender kind (rw_*.dds with an nb_rw_* channel map next to them)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from extract_fashion import Library  # noqa: E402

lib = Library()
keys = [k for k in lib.sorted_keys if '\\players\\装备\\' in k and k.endswith(('.dds', '.tga'))]
names = set(keys)
rw = [k for k in keys if k.rsplit('\\', 1)[-1].startswith('rw_')]
paired = [k for k in rw if k.rsplit('\\', 1)[0] + '\\nb_' + k.rsplit('\\', 1)[-1] in names]
nb = [k for k in keys if k.rsplit('\\', 1)[-1].startswith('nb_')]
print('rw_', len(rw), 'with nb_', len(paired), 'nb_ total', len(nb))
print('examples', paired[:3])
print('nb_ without rw_', [k for k in nb if k.rsplit('\\', 1)[0] + '\\' + k.rsplit('\\', 1)[-1][3:] not in names][:10])
