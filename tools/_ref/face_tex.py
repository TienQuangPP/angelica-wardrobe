"""Dump the face texture records a customize .ini names, and the meshes/textures of the face model.

py face_tex.py [ini]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import game_data  # noqa: E402
import ski_to_glb  # noqa: E402
from face_morph import read_ini  # noqa: E402
from ski_reader import parse  # noqa: E402

ini = read_ini(Path(sys.argv[1]))
gd = game_data.load()
for k in ("idFaceTex", "idEyeBaseTex", "idEyeHighTex", "idEyeBallTex", "idBrowTex", "idNoseTex", "idMouthTex",
          "idThirdEye", "idFalingSkin", "idFalingTex", "idHairTex", "idMoustacheTex"):
    v = ini.get(k)
    rec = gd["textures"].get(v) or gd["third_eye"].get(v) or gd["hairs"].get(v)
    print(f"{k:16s} {v:6} {rec}")
ski_to_glb._init_worker()
lib = ski_to_glb._lib
for n in (1, 2):
    key = rf"models\face\剑灵女标准脸\剑灵女标准脸{n}.ski".lower()
    if key in lib.files:
        sk = parse(lib.read(key))
        print(key, "textures", sk.textures)
        for m in sk.meshes:
            print("   ", m.name, "tex", m.texture, "verts", len(m.positions))
print([k for k in lib.files if k.startswith(r"models\face\剑灵女标准脸") and not k.endswith((".ski", ".bon"))][:60])
