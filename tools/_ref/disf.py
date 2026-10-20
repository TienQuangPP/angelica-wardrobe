"""Disassemble one function of elementclient.exe up to its first ret (or n bytes), annotating float constants and
calls with known names.

py disf.py <va hex> [max bytes] [--all]   (--all: do not stop at the first ret)
"""
import struct
import sys

import pe

va = int(sys.argv[1], 16)
n = int(sys.argv[2], 0) if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else 0x1000
stop = "--all" not in sys.argv
off = pe.va2off(va)
for i in pe.md.disasm(pe.raw[off:off + n], va):
    s = f"{i.address:#x} {i.mnemonic} {i.op_str}"
    if "[0x1" in i.op_str or "[0xa" in i.op_str:
        try:
            a = int(i.op_str.split("[0x")[1].split("]")[0], 16)
            o = pe.va2off(a)
            if o:
                f = struct.unpack("<f", pe.raw[o:o + 4])[0]
                d = struct.unpack("<d", pe.raw[o:o + 8])[0]
                s += f"   ; f={f:.6g} d={d:.6g}"
                if i.mnemonic == "push" or "offset" in i.op_str:
                    s += f" str={pe.cstr(a)[:40]!r}"
        except (ValueError, IndexError, struct.error):
            pass
    if i.mnemonic == "push" and i.op_str.startswith("0x1"):
        try:
            s += f"   ; str={pe.cstr(int(i.op_str, 16))[:50]!r}"
        except Exception:
            pass
    print(s)
    if stop and i.mnemonic == "ret":
        break
