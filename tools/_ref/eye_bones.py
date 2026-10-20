"""Names and bind positions of the face controller bones around the eye (BoneInit.cfg order)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ski_to_glb  # noqa: E402
from face_morph import FaceController  # noqa: E402

ski_to_glb._init_worker()
ctrl = FaceController(ski_to_glb._lib, r"models\face\剑灵女标准脸\剑灵女标准脸2.bon")
sys.stdout.reconfigure(encoding="utf-8")
for i in list(range(0, 30)) + [46, 47, 48, 50, 53, 56, 57, 62]:
    n = ctrl.order[i]
    print(i, n, ctrl.pos(i).round(4) if n in ctrl.M else "-")
for g, names in enumerate(ctrl.groups):
    print("group", g, names)
