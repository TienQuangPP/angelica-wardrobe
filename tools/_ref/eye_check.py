"""Where the eyeball mesh sits relative to its bone and to the eye hole of the face, before / after the morph."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import game_data  # noqa: E402
import ski_to_glb  # noqa: E402
from face_morph import FaceController, customise, posed_face, read_ini  # noqa: E402
from ski_reader import parse  # noqa: E402

ski_to_glb._init_worker()
lib = ski_to_glb._lib
ski = r"models\face\剑灵女标准脸\剑灵女标准脸2.ski"
bon = ski[:-4] + ".bon"
skin = parse(lib.read(ski))
ctrl = FaceController(lib, bon)
eyeball = skin.meshes[1]
print("skin bones used by eyeball:", sorted({skin.bones[i] for i in np.unique(eyeball.bone_ids[eyeball.weights.sum(1) > 0][:, 0])}))
for i in (13, 78):
    n = ctrl.order[i]
    print(i, n, "bone pos", ctrl.pos(i).round(4))
left = eyeball.positions[:, 0] > 0
for side, m in (("x>0", left), ("x<0", ~left)):
    p = eyeball.positions[m]
    print(side, "eyeball centroid", p.mean(0).round(4), "min", p.min(0).round(4), "max", p.max(0).round(4))
gd = game_data.load()
ini = read_ini(Path(sys.argv[1]))  # a saved customize .ini (element\\userdata\\character\\customize\\81)
shapes = {i: next((p for p in r["paths"] if p.lower().endswith(".eface")), None) for i, r in gd["face_shapes"].items()}
pose0 = posed_face(lib, ski, ctrl)
p0, _ = pose0(eyeball)
f0, _ = pose0(skin.meshes[0])
customise(lib, ctrl, ini, shapes)
pose1 = posed_face(lib, ski, ctrl)
p1, _ = pose1(eyeball)
f1, _ = pose1(skin.meshes[0])
for side, m in (("x>0", left), ("x<0", ~left)):
    print(side, "bind  eyeball min", p0[m].min(0).round(4), "max", p0[m].max(0).round(4))
    print(side, "morph eyeball min", p1[m].min(0).round(4), "max", p1[m].max(0).round(4))
# eye hole: face vertices near the eyeball in x/y, their z
for tag, f, p in (("bind", f0, p0), ("morph", f1, p1)):
    e = p[left]
    c = e.mean(0)
    r = np.abs(e - c).max(0)
    near = f[(np.abs(f[:, 0] - c[0]) < r[0] * 1.3) & (np.abs(f[:, 1] - c[1]) < r[1] * 1.3)]
    print(tag, "eye centre", c.round(4), "radius", r.round(4), "face z near eye: max", near[:, 2].max().round(4),
          "eyeball max z", e[:, 2].max().round(4))
