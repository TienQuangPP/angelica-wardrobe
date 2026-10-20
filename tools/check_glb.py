"""Verify every .glb below a folder: magic, version and declared length must match the file size."""
import struct
import sys
from pathlib import Path

root = Path(sys.argv[1])
bad, n = [], 0
for f in root.rglob("*.glb"):
    n += 1
    try:
        size = f.stat().st_size
        with open(f, "rb") as fh:
            head = fh.read(12)
        magic, version, length = struct.unpack("<III", head)
        if magic != 0x46546C67 or version != 2 or length != size:
            bad.append((f, f"header {magic:#x} v{version} len {length} size {size}"))
    except Exception as ex:
        bad.append((f, str(ex)))
print(f"checked {n} glb files, {len(bad)} bad")
for f, why in bad[:50]:
    print("  BAD", f, why)
