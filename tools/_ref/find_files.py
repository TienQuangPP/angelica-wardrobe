"""List game package files whose path contains every given word (case-insensitive).

py find_files.py word [word ...]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ski_to_glb  # noqa: E402

ski_to_glb._init_worker()
words = [w.lower() for w in sys.argv[1:]]
for k in sorted(ski_to_glb._lib.files):
    if all(w in k for w in words):
        print(k)
