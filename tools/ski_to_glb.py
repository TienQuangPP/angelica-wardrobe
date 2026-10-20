"""Convert the fashion .ski models listed in extracted_fashion/manifest.csv to .glb (binary glTF 2.0).

Usage:
    py tools/ski_to_glb.py --out=<data>\\3D [--all-lods] [--limit=N] [--workers=N] [category ...]

Each .ski becomes one .glb with its textures embedded (JPEG when opaque, PNG when the alpha channel
is a cut-out mask). Models stay in their bind pose. By default only the most detailed LOD
(一级, or files without a LOD suffix) is converted; 二级/三级 are lower-detail copies.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import struct
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from extract_fashion import OUT, Library, norm  # noqa: E402
from ski_reader import parse  # noqa: E402

LOW_LOD_RE = re.compile(r"(二级|三级)$")
MAX_TEXTURE: int | None = None  # downscale embedded textures (used for the large wardrobe scene)
# Folder that receives the game's own .dds files (wardrobe): the viewer samples them as the game does (same DXT
# blocks, same mipmaps) instead of the re-encoded preview embedded in the glb. Set by TGHM_DDS_DIR in workers.
DDS_DIR: Path | None = None
DDS_FOURCC = {b"DXT1", b"DXT3", b"DXT5"}
_lib: Library | None = None
_basename: dict[str, list[str]] = {}


def _init_worker() -> None:
    global _lib, _basename, DDS_DIR
    if os.environ.get("TGHM_DDS_DIR"):
        DDS_DIR = Path(os.environ["TGHM_DDS_DIR"])
    _lib = Library()
    for key in _lib.files:
        if key.endswith((".dds", ".tga", ".png", ".bmp", ".jpg")):
            _basename.setdefault(key.rsplit("\\", 1)[-1], []).append(key)


def _name_variants(name: str) -> list[str]:
    """Spellings the artists' material names drift into: stray spaces, .psd/.tga sources, rw_ prefix."""
    base = name.replace(" ", "")
    stem, _, ext = base.rpartition(".")
    stems = [stem, stem[3:] if stem.startswith("rw_") else "rw_" + stem]
    exts = [ext] + [e for e in ("dds", "tga") if e != ext]
    return [name] + [f"{s}.{e}" for s in stems for e in exts]


def _closest_in(folders: list[str], name: str) -> str | None:
    """Most similar colour texture (not a nb_ normal map): first in the model's texture folders, then anywhere.
    The last two characters name the piece (头发, 下身, 鞋子...) and must overlap."""
    import difflib
    stem = Path(name).stem.replace(" ", "")
    stem = stem[3:] if stem.startswith("rw_") else stem

    def pick(keys, threshold):
        best, score = None, threshold
        for key in keys:
            fname = key.rsplit("\\", 1)[-1]
            if not fname.endswith((".dds", ".tga")) or fname.startswith("nb_"):
                continue
            other = Path(fname).stem
            other = other[3:] if other.startswith("rw_") else other
            if not set(other[-2:]) & set(stem[-2:]):  # 头发 ~ 男头, but 下身 != 鞋子
                continue
            r = difflib.SequenceMatcher(None, stem, other).ratio()
            if r > score:
                best, score = key, r
        return best

    local = [k for f in folders for k in _lib.under(f + "\\") if k.count("\\") == f.count("\\") + 1]
    return pick(local, 0.6) or pick((k for keys in _basename.values() for k in keys), 0.85)


def find_texture(ski_key: str, name: str) -> str | None:
    name = norm(name).lower()
    folder = ski_key.rsplit("\\", 1)[0]
    parent = folder.rsplit("\\", 1)[0]
    folders = [f"{folder}\\textures", folder, f"{parent}\\textures", parent]
    for variant in _name_variants(name):
        for f in folders:
            if f"{f}\\{variant}" in _lib.files:
                return f"{f}\\{variant}"
    options = _basename.get(name.rsplit("\\", 1)[-1], [])
    if not options:
        # e.g. 'rw_火龙果时装女头发.dds' is stored as 'rw_盲盒火龙果时装女头发.dds'
        return _closest_in(folders[:1] + folders[2:3], name)

    def shared(path: str) -> int:
        a, b = path.split("\\"), ski_key.split("\\")
        n = 0
        while n < min(len(a), len(b)) and a[n] == b[n]:
            n += 1
        return n

    return max(options, key=shared)


def encode_texture(key: str, mode: str = "auto") -> tuple[bytes, str, bool] | None:
    """Return (image bytes, mime type, uses alpha cut-out) or None if the texture can't be decoded.

    mode "dye": the alpha channel is the fashion dye mask of the game's fashion shader
    (rgb = lerp(tex, tex * colour, tex.a), always opaque) - keep it in a WebP, never cut out.
    mode "cutout": like "auto", cut-outs stored as WebP (fashion textures with an nb_ channel map).
    """
    try:
        img = Image.open(io.BytesIO(_lib.read(key)))
        img.load()
    except Exception:
        return None
    img = img.convert("RGBA")
    if MAX_TEXTURE and max(img.size) > MAX_TEXTURE:
        img.thumbnail((MAX_TEXTURE, MAX_TEXTURE))
    alpha = np.asarray(img.getchannel("A"))
    if mode == "dye":
        buf = io.BytesIO()
        if alpha.min() < 250:
            img.save(buf, "WEBP", quality=92, alpha_quality=100, method=4)
            return buf.getvalue(), "image/webp", False
        img.convert("RGB").save(buf, "JPEG", quality=92)
        return buf.getvalue(), "image/jpeg", False
    if mode == "cutout":
        # rewurender textures (rw_ + nb_ channel map): any alpha is transparency, alpha-blended by the engine
        # (rewurender.hlsl outputs diffuse.a * tex.a; the lace of a stocking is half see-through)
        buf = io.BytesIO()
        if alpha.min() < 250:
            img.save(buf, "WEBP", quality=92, alpha_quality=100, method=4)
            return buf.getvalue(), "image/webp", "blend"
        img.convert("RGB").save(buf, "JPEG", quality=92)
        return buf.getvalue(), "image/jpeg", False
    clear = (alpha < 32).mean()
    middle = ((alpha >= 64) & (alpha <= 192)).mean()
    # Cut-out (lace, hair strands, frills): many fully clear pixels and few half-transparent ones.
    # Otherwise the alpha channel is a gloss/glow mask in this engine and must be ignored.
    cutout = 0.02 < clear < 0.98 and middle < 0.25
    buf = io.BytesIO()
    if cutout:
        img.save(buf, "PNG", optimize=False, compress_level=6)
        return buf.getvalue(), "image/png", True
    img.convert("RGB").save(buf, "JPEG", quality=90)
    return buf.getvalue(), "image/jpeg", False


def dds_copy(key: str | None) -> str | None:
    """Copy a game .dds (DXT1/3/5 with its mipmaps) into DDS_DIR under a content hash; return the file name."""
    if DDS_DIR is None or not key or not key.endswith(".dds"):
        return None
    import hashlib
    data = _lib.read(key)
    if len(data) < 128 or data[:4] != b"DDS " or data[84:88] not in DDS_FOURCC:
        return None
    name = hashlib.sha1(data).hexdigest()[:20] + ".dds"
    path = DDS_DIR / name
    if not path.exists():
        DDS_DIR.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_bytes(data)
        try:
            os.replace(tmp, path)
        except OSError:
            tmp.unlink(missing_ok=True)
    return name


def channel_map(key: str) -> str | None:
    """Channel texture of a newer fashion texture (rewurender.hlsl): <folder>\\nb_<name> next to rw_<name>.

    Its blue channel is the dye mask and green the reflection strength; the rw_ texture's own alpha is then
    plain transparency. A few folders name it after a colour variant: take their only nb_ file.
    """
    folder, fname = key.rsplit("\\", 1)
    exact = f"{folder}\\nb_{fname}"
    if exact in _lib.files:
        return exact
    others = [k for k in _lib.under(folder + "\\") if k.rsplit("\\", 1)[-1].startswith("nb_")]
    return others[0] if fname.startswith("rw_") and len(others) == 1 else None


def encode_channel(key: str) -> tuple[bytes, str] | None:
    try:
        img = Image.open(io.BytesIO(_lib.read(key)))
        img.load()
    except Exception:
        return None
    img = img.convert("RGB")
    if MAX_TEXTURE and max(img.size) > MAX_TEXTURE:
        img.thumbnail((MAX_TEXTURE, MAX_TEXTURE))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue(), "image/jpeg"


MIRROR = np.diag([1.0, 1.0, -1.0, 1.0])


def mirror(m_row: np.ndarray) -> np.ndarray:
    """Game (left-handed, row-vector) 4x4 -> right-handed column-vector matrix."""
    return MIRROR @ np.asarray(m_row, np.float64).T @ MIRROR


def decompose(m: np.ndarray) -> tuple[list[float], list[float]]:
    """Column-vector 4x4 -> (translation, quaternion xyzw); scale is dropped."""
    u, _, vt = np.linalg.svd(m[:3, :3])
    r = u @ vt
    if np.linalg.det(r) < 0:
        u[:, -1] *= -1
        r = u @ vt
    tr = np.trace(r)
    if tr > 0:
        s = np.sqrt(tr + 1.0) * 2
        q = [(r[2, 1] - r[1, 2]) / s, (r[0, 2] - r[2, 0]) / s, (r[1, 0] - r[0, 1]) / s, 0.25 * s]
    elif r[0, 0] > r[1, 1] and r[0, 0] > r[2, 2]:
        s = np.sqrt(1.0 + r[0, 0] - r[1, 1] - r[2, 2]) * 2
        q = [0.25 * s, (r[0, 1] + r[1, 0]) / s, (r[0, 2] + r[2, 0]) / s, (r[2, 1] - r[1, 2]) / s]
    elif r[1, 1] > r[2, 2]:
        s = np.sqrt(1.0 + r[1, 1] - r[0, 0] - r[2, 2]) * 2
        q = [(r[0, 1] + r[1, 0]) / s, 0.25 * s, (r[1, 2] + r[2, 1]) / s, (r[0, 2] - r[2, 0]) / s]
    else:
        s = np.sqrt(1.0 + r[2, 2] - r[0, 0] - r[1, 1]) * 2
        q = [(r[0, 2] + r[2, 0]) / s, (r[1, 2] + r[2, 1]) / s, 0.25 * s, (r[1, 0] - r[0, 1]) / s]
    q = np.array(q) / np.linalg.norm(q)
    return [float(x) for x in m[:3, 3]], [float(x) for x in q]


class Skeleton:
    """Skin index in a GlbBuilder plus bone-name -> joint lookup."""

    def __init__(self, skin: int, joints: dict[str, int]):
        self.skin = skin
        self.joints = joints
        self.base_names: list[str] = []  # bone order used by .ski files without their own bone list
        self.rigid: str | None = None  # bind every vertex to this bone (fashion hair on the head)
        self.fallback = joints.get("Bip01 Pelvis", 0)

    def joint(self, name: str) -> int:
        return self.joints.get(name, self.fallback)


class GlbBuilder:
    def __init__(self) -> None:
        self.bin = bytearray()
        self.gltf = {
            "asset": {"version": "2.0", "generator": "TGHM ski_to_glb"},
            "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [], "meshes": [],
            "buffers": [], "bufferViews": [], "accessors": [],
            "materials": [], "textures": [], "images": [], "samplers": [{"wrapS": 10497, "wrapT": 10497}],
        }

    def _view(self, data: bytes, target: int | None = None) -> int:
        while len(self.bin) % 4:
            self.bin.append(0)
        view = {"buffer": 0, "byteOffset": len(self.bin), "byteLength": len(data)}
        if target:
            view["target"] = target
        self.bin += data
        self.gltf["bufferViews"].append(view)
        return len(self.gltf["bufferViews"]) - 1

    def accessor(self, arr: np.ndarray, kind: str, component: int, target: int, minmax: bool = False) -> int:
        acc = {"bufferView": self._view(arr.tobytes(), target), "componentType": component,
               "count": int(arr.shape[0]), "type": kind}
        if minmax:
            acc["min"] = arr.min(axis=0).astype(float).tolist()
            acc["max"] = arr.max(axis=0).astype(float).tolist()
        self.gltf["accessors"].append(acc)
        return len(self.gltf["accessors"]) - 1

    def image(self, data: bytes, mime: str) -> int:
        self.gltf["images"].append({"bufferView": self._view(data), "mimeType": mime})
        self.gltf["textures"].append({"source": len(self.gltf["images"]) - 1, "sampler": 0})
        return len(self.gltf["textures"]) - 1

    def material(self, name: str, texture: int | None, cutout, dye: bool = False,
                 channel: int | None = None, dds: dict | None = None) -> int:
        pbr = {"metallicFactor": 0.0, "roughnessFactor": 1.0}
        if texture is None:
            pbr["baseColorFactor"] = [0.7, 0.7, 0.7, 1.0]
        else:
            pbr["baseColorTexture"] = {"index": texture}
        mat = {"name": name, "pbrMetallicRoughness": pbr, "doubleSided": True}
        if cutout == "blend":
            mat["alphaMode"] = "BLEND"
        elif cutout:
            mat["alphaMode"] = "MASK"
            mat["alphaCutoff"] = 0.5
        extras = dict(dds or {})
        if dye:  # texture alpha = dye mask (see encode_texture); the viewer applies the fashion colour
            extras["dyeMask"] = True
        if channel is not None:  # rewurender: the channel map rides in the occlusion slot (b = dye, g = reflection)
            mat["occlusionTexture"] = {"index": channel}
            extras["dyeChannel"] = True
        if extras:
            mat["extras"] = extras
        self.gltf["materials"].append(mat)
        return len(self.gltf["materials"]) - 1

    def add_mesh(self, name: str, primitives: list[dict], skin: int | None = None) -> None:
        self.gltf["meshes"].append({"name": name, "primitives": primitives})
        node = {"name": name, "mesh": len(self.gltf["meshes"]) - 1}
        if skin is not None:
            node["skin"] = skin
        self.gltf["nodes"].append(node)

    def add_skeleton(self, bones) -> "Skeleton":
        """Joint nodes + skin for an Angelica skeleton (bind pose), converted to right-handed space."""
        base = len(self.gltf["nodes"])
        for b in bones:
            t, q = decompose(mirror(b.relative))
            self.gltf["nodes"].append({"name": b.name, "translation": t, "rotation": q})
        for i, b in enumerate(bones):
            if b.parent >= 0:
                self.gltf["nodes"][base + b.parent].setdefault("children", []).append(base + i)
        ibm = np.stack([mirror(b.init).T.reshape(-1) for b in bones]).astype(np.float32)  # column-major
        acc = self.accessor(ibm, "MAT4", 5126, None)
        roots = [base + i for i, b in enumerate(bones) if b.parent < 0]
        self.gltf.setdefault("skins", []).append(
            {"joints": list(range(base, base + len(bones))), "inverseBindMatrices": acc, "skeleton": roots[0]})
        return Skeleton(len(self.gltf["skins"]) - 1, {b.name: i for i, b in enumerate(bones)})

    def finish(self, name: str | None = None, primitives: list[dict] | None = None,
               extras: dict | None = None) -> bytes:
        if primitives:
            self.add_mesh(name, primitives)
        children = {c for n in self.gltf["nodes"] for c in n.get("children", [])}
        self.gltf["scenes"] = [{"nodes": [i for i in range(len(self.gltf["nodes"])) if i not in children]}]
        if not self.gltf.get("skins"):
            self.gltf.pop("skins", None)
        if extras:
            self.gltf["scenes"][0]["extras"] = extras
        self.gltf["buffers"].append({"byteLength": len(self.bin)})
        for k in ("textures", "images", "materials"):
            if not self.gltf[k]:
                del self.gltf[k]
        if "textures" not in self.gltf:
            del self.gltf["samplers"]
        js = json.dumps(self.gltf, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        js += b" " * (-len(js) % 4)
        binary = bytes(self.bin) + b"\0" * (-len(self.bin) % 4)
        total = 12 + 8 + len(js) + 8 + len(binary)
        return (struct.pack("<III", 0x46546C67, 2, total) + struct.pack("<II", len(js), 0x4E4F534A) + js
                + struct.pack("<II", len(binary), 0x004E4942) + binary)


def skin_attributes(glb: GlbBuilder, skin, mesh, skel: Skeleton) -> dict:
    """JOINTS_0 / WEIGHTS_0 accessors for one mesh bound to `skel`."""
    n = len(mesh.positions)
    if skel.rigid:
        joints = np.zeros((n, 4), np.uint16)
        joints[:, 0] = skel.joint(skel.rigid)
        weights = np.zeros((n, 4), np.float32)
        weights[:, 0] = 1
    else:
        names = skin.bones or skel.base_names
        lookup = np.array([skel.joint(nm) for nm in names] + [skel.fallback], np.uint16)
        if mesh.bone_ids is None:  # rigid mesh on one bone
            ids = np.full((n, 4), min(max(mesh.bone, 0), len(lookup) - 1))
            weights = np.zeros((n, 4), np.float32)
            weights[:, 0] = 1
        else:
            ids = np.minimum(mesh.bone_ids.astype(np.int64), len(lookup) - 1)
            weights = np.zeros((n, 4), np.float32)
            weights[:, :3] = mesh.weights
            weights[:, 3] = np.clip(1 - mesh.weights.sum(1), 0, 1)
        joints = lookup[ids]
        total = weights.sum(1, keepdims=True)
        weights = np.where(total > 1e-6, weights / np.maximum(total, 1e-6), np.array([1, 0, 0, 0], np.float32))
        weights[weights < 1e-4] = 0  # unused influences must not point at random joints
        joints = np.where(weights > 0, joints, 0).astype(np.uint16)
    return {
        "JOINTS_0": glb.accessor(np.ascontiguousarray(joints), "VEC4", 5123, 34962),
        "WEIGHTS_0": glb.accessor(np.ascontiguousarray(weights, np.float32), "VEC4", 5126, 34962),
    }


def add_skin(glb: GlbBuilder, ski_key: str, name: str, materials: dict, warnings: list[str],
             keep=None, offset=None, skel: Skeleton | None = None, alpha: str = "auto", pose=None) -> int:
    """Append the meshes of one .ski as a node of `glb`. Returns the number of primitives added.

    `materials` caches materials by texture path so parts sharing a texture embed it once.
    `keep(mesh, texture_name)` can drop sub-meshes (e.g. the default hair when a fashion hair is worn).
    `skel` (from glb.add_skeleton) exports the mesh skinned to that skeleton so it can be animated.
    `alpha`: "auto" guesses cut-outs; "dye" keeps the alpha as the fashion dye mask (opaque material).
    `pose(mesh) -> (positions, normals)` replaces the bind-pose vertices (e.g. a customised face).
    """
    skin = parse(_lib.read(ski_key))

    def material_for(tex_index: int) -> int:
        tex_name = skin.textures[tex_index] if 0 <= tex_index < len(skin.textures) else ""
        key = find_texture(ski_key, tex_name) if tex_name else None
        cache_key = key or f"missing:{tex_name}"
        if cache_key not in materials:
            tex_id, cutout, dye, channel = None, False, False, None
            # newer fashions (rewurender): dye mask in the nb_ channel map, the texture's alpha is transparency
            ch_key = channel_map(key) if key and alpha == "dye" else None
            ch = encode_channel(ch_key) if ch_key else None
            encoded = encode_texture(key, "cutout" if ch else alpha) if key else None
            if encoded:
                tex_id = glb.image(encoded[0], encoded[1])
                cutout = encoded[2]
                dye = alpha == "dye" and not ch and encoded[1] == "image/webp"
                if ch:
                    channel = glb.image(*ch)
            elif tex_name:
                warnings.append(f"texture {'undecodable' if key else 'missing'}: {tex_name}")
            dds = {}
            if tex_id is not None and (name := dds_copy(key)):
                dds["dds"] = name
                if channel is not None and (cname := dds_copy(ch_key)):
                    dds["ddsChannel"] = cname
            materials[cache_key] = glb.material(tex_name or "none", tex_id, cutout, dye, channel, dds)
        return materials[cache_key]

    primitives = []
    for mesh in skin.meshes:
        tri = len(mesh.indices) // 3 * 3
        if tri == 0 or len(mesh.positions) == 0:
            continue
        if keep and not keep(mesh, skin.textures[mesh.texture] if 0 <= mesh.texture < len(skin.textures) else ""):
            continue
        # Angelica is left-handed (D3D); glTF is right-handed: mirror Z and flip the winding.
        if pose is not None:
            pos, nrm = (np.array(a, np.float32) for a in pose(mesh))
        else:
            pos, nrm = mesh.positions.astype(np.float32), mesh.normals.copy()
        if offset is not None:  # models authored relative to a hook (e.g. fashion hair on the head)
            pos = pos + np.asarray(offset, np.float32)
        pos[:, 2] *= -1
        nrm[:, 2] *= -1
        length = np.linalg.norm(nrm, axis=1, keepdims=True)
        nrm = np.where(length > 1e-6, nrm / np.maximum(length, 1e-6), np.array([0, 1, 0], np.float32))
        idx = mesh.indices[:tri].reshape(-1, 3)[:, [0, 2, 1]].reshape(-1).astype(np.uint16)
        attributes = {
            "POSITION": glb.accessor(np.ascontiguousarray(pos, np.float32), "VEC3", 5126, 34962, True),
            "NORMAL": glb.accessor(np.ascontiguousarray(nrm, np.float32), "VEC3", 5126, 34962),
            "TEXCOORD_0": glb.accessor(np.ascontiguousarray(mesh.uvs, np.float32), "VEC2", 5126, 34962),
        }
        if skel is not None:
            attributes.update(skin_attributes(glb, skin, mesh, skel))
        primitives.append({
            "attributes": attributes,
            "indices": glb.accessor(idx, "SCALAR", 5123, 34963),
            "material": material_for(mesh.texture),
        })
    if primitives:
        glb.add_mesh(name, primitives, skel.skin if skel is not None else None)
    return len(primitives)


def convert(ski_key: str) -> tuple[bytes, list[str]]:
    glb = GlbBuilder()
    warnings: list[str] = []
    if not add_skin(glb, ski_key, Path(ski_key).stem, {}, warnings):
        raise ValueError("no geometry")
    return glb.finish(), warnings


def work(batch: list[tuple[str, str]], out_root: str) -> list[tuple[str, str, str]]:
    results = []
    for category, ski_key in batch:
        pkg, entry = _lib.files[ski_key]
        dest = Path(out_root) / category / Path(norm(entry.path)).with_suffix(".glb")
        try:
            data, warnings = convert(ski_key)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open("\\\\?\\" + str(dest.resolve()), "wb") as fh:
                fh.write(data)
            results.append((ski_key, "ok", "; ".join(warnings)))
        except Exception as ex:  # keep going; failures are listed in the report
            results.append((ski_key, "error", f"{type(ex).__name__}: {ex}"))
    return results


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    opts = dict(a[2:].split("=", 1) if "=" in a else (a[2:], "1") for a in sys.argv[1:] if a.startswith("--"))
    out_root = Path(opts.get("out", str(OUT / "3D")))
    workers = int(opts.get("workers", max(1, (os.cpu_count() or 2) - 1)))
    limit = int(opts.get("limit", 0))

    with open(OUT / "manifest.csv", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    jobs = []
    for row in rows:
        path = row["path"]
        if not path.lower().endswith(".ski") or (args and row["category"] not in args):
            continue
        if "all-lods" not in opts and LOW_LOD_RE.search(Path(path.replace("\\", "/")).stem):
            continue
        jobs.append((row["category"], norm(path).lower()))
    jobs.sort(key=lambda j: j[1])
    if limit:
        jobs = jobs[:limit]
    print(f"{len(jobs)} models -> {out_root} with {workers} workers", flush=True)

    # Batches of neighbouring files keep each worker inside one folder.
    batches = [jobs[i:i + 40] for i in range(0, len(jobs), 40)]
    report = []
    start = time.time()
    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker) as pool:
        futures = [pool.submit(work, b, str(out_root)) for b in batches]
        for n, fut in enumerate(as_completed(futures), 1):
            report += fut.result()
            if n % 25 == 0 or n == len(futures):
                done = len(report)
                print(f"  {done}/{len(jobs)}  {time.time() - start:.0f}s", flush=True)

    out_root.mkdir(parents=True, exist_ok=True)
    with open(out_root / "convert_report.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["ski", "status", "note"])
        w.writerows(sorted(report))
    ok = sum(1 for r in report if r[1] == "ok")
    warned = sum(1 for r in report if r[1] == "ok" and r[2])
    print(f"converted {ok}/{len(report)} ({warned} with texture warnings); report: {out_root / 'convert_report.csv'}")


if __name__ == "__main__":
    main()
