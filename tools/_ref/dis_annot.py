"""Disassemble a function with string / float annotations for immediates: dis_annot.py <va hex> <out> [max]"""
import re
import struct
import sys

sys.path.insert(0, str(Path(__file__).parent))
import pe  # noqa: E402

va = int(sys.argv[1], 16)
out_path = sys.argv[2]
limit = int(sys.argv[3]) if len(sys.argv) > 3 else 4000
off = pe.va2off(va)
lines = []
for ins in pe.md.disasm(pe.raw[off:off + limit * 8], va):
    s = f'{ins.address:08x} {ins.mnemonic} {ins.op_str}'
    for m in re.findall(r'0x[0-9a-f]{6,8}', ins.op_str):
        v = int(m, 16)
        o = pe.va2off(v)
        if not o or v < pe.TEXT[1] + pe.TEXT[2]:
            continue
        b = pe.raw[o:o + 64]
        if len(b) < 8:
            continue
        txt = b.split(b'\0')[0]
        if len(txt) >= 3 and all(32 <= c < 127 or c >= 0x81 for c in txt):
            s += '   ; "' + txt.decode('gbk', 'replace') + '"'
        else:
            s += '   ; f=%g d=%g' % (struct.unpack('<f', b[:4])[0], struct.unpack('<d', b[:8])[0])
    lines.append(s)
    if ins.mnemonic == 'ret' or len(lines) >= limit:
        break
open(out_path, 'w', encoding='utf-8').write('\n'.join(lines))
print(len(lines))
