"""Print a text file from the game packages (gbk / utf-16 / utf-8 guessed) or save a binary one.

py pck_cat.py <key> [out_file] [max_chars]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ski_to_glb  # noqa: E402

ski_to_glb._init_worker()
key = sys.argv[1].lower()
data = ski_to_glb._lib.read(key)
if len(sys.argv) > 2 and sys.argv[2] != "-":
    Path(sys.argv[2]).write_bytes(data)
    print("saved", len(data))
else:
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = data.decode("utf-16")
    else:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("gbk", "replace")
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 20000
    sys.stdout.reconfigure(encoding="utf-8")
    print(text[:n])
