"""Reader for the Angelica 2.2 material files (.mtl) of the HD fashion models (models2\\...\\通用高模).

The files are XOR 0x8E obfuscated. Layout after decoding:
    shader path, macros ("AMBIENT_AFFECT_ENV;ENABLE_TINT;"), then parameters: name, then either a texture
    path (samplers) or a value ("1.000", "(1.000,1.000,1.000,1.000)").
"""
from __future__ import annotations

import re
import struct


def decode(raw: bytes) -> bytes:
    return bytes(b ^ 0x8E for b in raw)


def parse(raw: bytes) -> dict:
    d = decode(raw)
    # every string is stored as u32 length + bytes (GBK)
    out: dict = {"params": {}}
    strings = []
    p = 0
    while p + 4 <= len(d):
        n = struct.unpack_from("<I", decode(raw[p:p + 4]) if False else d, p)[0]
        if 0 < n < 512 and p + 4 + n <= len(d):
            s = d[p + 4:p + 4 + n]
            if all(32 <= c < 127 or c >= 0x80 for c in s):
                strings.append(s.decode("gbk", "replace"))
                p += 4 + n
                continue
        p += 1
    out["strings"] = strings
    for i, s in enumerate(strings):
        if s.endswith(".hlsl"):
            out["shader"] = s
        elif s.endswith(";") and s.isupper():
            out["macros"] = [m for m in s.split(";") if m]
    for i, s in enumerate(strings[:-1]):
        if s.startswith("g_"):
            v = strings[i + 1]
            m = re.fullmatch(r"\(([-\d.,]+)\)", v)
            if m:
                out["params"][s] = [float(x) for x in m.group(1).split(",")]
            elif re.fullmatch(r"-?[\d.]+", v):
                out["params"][s] = float(v)
            elif not v.startswith("g_"):
                out["params"][s] = v
    return out


if __name__ == "__main__":
    import json
    import sys

    for path in sys.argv[1:]:
        raw = open(path, "rb").read()
        print(path)
        print(json.dumps(parse(raw), ensure_ascii=False, indent=1))
