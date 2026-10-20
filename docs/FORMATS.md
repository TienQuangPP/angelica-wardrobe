# File formats and engine notes

Everything here was found by reading the client's files and its 32-bit executable; the parsers in `tools/`
are the reference implementation.

## Packages (`.pck` / `.pkx` / `.pkx1`), version 0x00020003
- 288-byte tail; index offset and entry table are XOR-masked with 0xA8937462 / 0xF1A43653.
- Entries are zlib-compressed; paths are GBK, some use `/` instead of `\`. A package can span `.pck`+`.pkx`+`.pkx1`.

## `elements.data` (version 0x30000213)
- Not encrypted: after a small header come the lists, each `count, count × (u32 id, u16 size), u32 total, blobs`.
- Every record is compressed on its own with MPPC (RFC 2118, 8 KB history) into a struct of the list's size.
- Lists used: 82 fashion items, 193 fashion sets, 341 collection groups, 342 illustrations, 58 face textures,
  59 face shapes (`.eFace`), 62 hair models, 135 third-eye effects. Offsets are documented in `game_data.py`.

## Models
- `.ski` (MOXBIKSA) v8 / v9 / v101: 108-byte header, skin vertex 48 bytes; v101 (HD) appends float4 tangents
  after the indices. v9 clothing bone lists need the class's "ex" skeleton (cloth bones).
- `.bon` (MOXBEKSA): bones (parent, relative and initial matrices, D3D row vectors), then hooks
  (`HH_` / `CC_`: name, type, bone, 4×4 matrix).
- `.stck` (MOXBKCTS): per-bone position and rotation tracks; v2 may store rotations as float3 (w rebuilt).
- The engine is left-handed (D3D): the exporter mirrors Z and flips the winding for glTF.
- Fashion hair / face models live in face space: offset +1.570 (female) / +1.743 (male) on Y.

## Shaders (fashion)
- `fashionrender.hlsl` (older fashions): texture alpha is a **dye mask**, `rgb = lerp(tex, tex × colour, a)`, opaque.
- `rewurender.hlsl` (newer fashions, `rw_*.dds`): the `nb_*` channel map holds the dye mask (blue) and the
  reflection strength (green, × `armorreflect.bmp`); the texture alpha is transparency (alpha-blended).
- Lighting and dyeing happen on raw texture values (gamma space); doing it in linear space turns dyed reds pink.
- `eyeballrender.hlsl`: iris = base × pupil colour, then the highlight texture by its alpha, then a gloss map.

## Character creator (face)
- `Configs\BoneInit.cfg` (controller bone order: 46 left / centre, 19 centre, right side = left + 65),
  `BoneGroup.cfg` (19 groups), `BonePart.cfg` (3 face parts).
- Slider `v` (0–255): `scale = 1 + (v−128)/128 · min(factor, cap)`, `offset = (v−128)/128 · min(factor, cap)`;
  factor defaults are hard-coded in the client (no `CustomizeFactor.ini` shipped).
- Operations on bone matrices: MOVE, ROTATE (D3DX X·Y·Z about a centre), SCALE (own frame / selection centre /
  pivot bone); `.eFace` shapes are weighted per-bone translation deltas. The eyeball is scaled about
  (its x, its y, mean z of the inner and outer eye corners).
- In the world the client draws the standard class head (`形象\<class>\头\<class>头N.ski`); the sculpted
  `models\face\<class>标准脸N` face is used by the creator / fashion preview.

## Body shape
- Standard models: `facedata\躯干参数\低模<男|女>\*.ini` list bones with flags (length, thickness, whole, special);
  every group uses factor 0.99: `s = 1 + (v−128)/128 · 0.99`.
- Engine bone rules: a bone's length / thickness scale the segment from its parent (in the parent's skin
  matrix, along the parent→bone direction; a leaf thickens its own segment); the length also moves the joint
  (relative translation × parent whole × length); whole scale is inherited.

## Rendering settings worth copying
- No MSAA; `systemsettings.ini` `MipMapBias = 1` → sharper mip levels (≈ −1 LOD bias).
