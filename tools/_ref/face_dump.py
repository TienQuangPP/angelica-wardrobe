"""Save the face texture layers of a customize .ini (and the face/eyeball textures) as PNG for inspection.

py face_dump.py [out_dir]
"""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ski_to_glb  # noqa: E402
from extract_fashion import norm  # noqa: E402
from PIL import Image  # noqa: E402
from tghm_paths import REF  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else REF / "face")
out.mkdir(parents=True, exist_ok=True)
ski_to_glb._init_worker()
lib = ski_to_glb._lib
keys = [
    r"models\face\剑灵女标准脸\tex_剑灵女标准脸2\rw_头02.dds",
    r"models\face\剑灵女标准脸\tex_剑灵女标准脸2\nb_rw_头02.dds",
    r"models\face\剑灵女标准脸\tex_剑灵女标准脸2\眼珠b01.dds",
    r"models\face\剑灵女标准脸\tex_剑灵女标准脸2\眼珠a01.dds",
]
for f in ("眼型", "眉型", "鼻型", "嘴型"):
    keys += [k for k in lib.under(rf"facedata\法师女\个性化\五官贴图库\{f}") if k.endswith(".dds")][:4]
keys += [k for k in lib.under(r"facedata\灵族女\个性化\五官贴图库") if k.endswith(".dds")][:12]
keys += [k for k in lib.under(r"facedata\法师女\法令模型库\textures")][:2]
for k in keys:
    k = norm(k).lower()
    if k not in lib.files:
        print("missing", k)
        continue
    img = Image.open(io.BytesIO(lib.read(k)))
    a = img.convert("RGBA")
    ex = a.getextrema()
    name = k.replace("\\", "_")[-60:]
    a.save(out / (Path(name).stem + ".png"))
    print(f"{k}  {img.mode} {img.size} alpha {ex[3]}")
