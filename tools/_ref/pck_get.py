"""Copy files out of the client packs: py pck_get.py <dest dir> <key> [key ...] (keys may use / or \\)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from extract_fashion import Library  # noqa: E402

lib = Library()
dest = Path(sys.argv[1])
dest.mkdir(parents=True, exist_ok=True)
for k in sys.argv[2:]:
    key = k.replace('/', '\\').lower()
    data = lib.read(key)
    (dest / Path(key.replace('\\', '/')).name).write_bytes(data)
    print(key, len(data))
