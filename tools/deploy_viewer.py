"""Copy the viewer pages (tools/viewer) next to the generated data (<data>/3D) so the local server can serve them.

py tools/deploy_viewer.py [--out=<data>\\3D]
three.js r160 is not part of this repository: run tools/viewer/get_three.ps1 once (it downloads the six module
files the pages import into <data>/3D/lib/three).
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tghm_paths import DATA  # noqa: E402

VIEWER = Path(__file__).parent / "viewer"
FILES = ["tu_do.html", "tu_do.js", "aui.js", "fx.js", "xem_3d.html", "server.ps1", "XEM_TU_DO.bat", "XEM_3D.bat"]

opts = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--") and "=" in a)
out = Path(opts.get("out", str(DATA / "3D")))
out.mkdir(parents=True, exist_ok=True)
for name in FILES:
    shutil.copy2(VIEWER / name, out / name)
    print("copied", name)
exe = VIEWER / "launcher" / "TuDoThoiTrang.exe"
if exe.exists():
    shutil.copy2(exe, out / exe.name)
    print("copied", exe.name)
if not (out / "lib" / "three" / "build" / "three.module.js").exists():
    print("three.js missing: run tools/viewer/get_three.ps1 -Out", out)
