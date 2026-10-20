"""Tiny helpers to explore elementclient.exe (32-bit): string lookup, xrefs, disassembly."""
import re
import struct
import sys

import capstone
import pefile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tghm_paths import DATA, ELEMENT, REF  # noqa: E402

EXE = str(ELEMENT / 'elementclient.exe')
pe = pefile.PE(EXE, fast_load=True)
BASE = pe.OPTIONAL_HEADER.ImageBase
raw = open(EXE, 'rb').read()
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
md.detail = False
SECTIONS = [(s.Name.rstrip(b'\0').decode(), BASE + s.VirtualAddress, s.Misc_VirtualSize, s.PointerToRawData, s.SizeOfRawData)
            for s in pe.sections]
TEXT = next(s for s in SECTIONS if s[0] == '.text')


def off2va(off):
    for name, va, vs, ro, rs in SECTIONS:
        if ro <= off < ro + rs:
            return va + off - ro
    return None


def va2off(va):
    for name, sva, vs, ro, rs in SECTIONS:
        if sva <= va < sva + max(vs, rs):
            return ro + va - sva
    return None


def strings(pat: bytes):
    return [(m.start(), off2va(m.start())) for m in re.finditer(pat, raw)]


def xrefs(va):
    """Offsets in .text that contain the 4-byte immediate va."""
    needle = struct.pack('<I', va)
    _, tva, tvs, tro, trs = TEXT
    out = []
    i = raw.find(needle, tro, tro + trs)
    while i >= 0:
        out.append(off2va(i))
        i = raw.find(needle, i + 1, tro + trs)
    return out


def calls_to(target):
    """VAs of E8 rel32 calls to target."""
    _, tva, tvs, tro, trs = TEXT
    out = []
    data = raw[tro:tro + trs]
    for m in re.finditer(b'\xe8', data):
        i = m.start()
        if i + 5 > len(data):
            break
        rel = struct.unpack_from('<i', data, i + 1)[0]
        va = tva + i
        if va + 5 + rel == target:
            out.append(va)
    return out


def dis(va, n=60, stop_ret=False):
    off = va2off(va)
    code = raw[off:off + n * 8]
    lines = []
    for ins in md.disasm(code, va):
        lines.append(f'{ins.address:08x}  {ins.mnemonic:6s} {ins.op_str}')
        if len(lines) >= n or (stop_ret and ins.mnemonic == 'ret'):
            break
    return '\n'.join(lines)


def find_func_start(va, back=4096):
    """Heuristic: scan backwards for the int3/nop padding + push ebp / sub esp prologue."""
    off = va2off(va)
    for i in range(off, off - back, -1):
        if raw[i - 1] in (0xcc, 0x90, 0xc3) and raw[i] in (0x55, 0x83, 0x81, 0x6a, 0x56, 0x53, 0x8b, 0x51, 0x64, 0x57):
            if raw[i - 2] in (0xcc, 0x90, 0xc3, 0xc2) or raw[i - 1] == 0xc3:
                return off2va(i)
    return None


def cstr(va, maxlen=200):
    off = va2off(va)
    s = raw[off:off + maxlen].split(b'\0')[0]
    return s.decode('gbk', 'replace')


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'str':
        for off, va in strings(sys.argv[2].encode()):
            print(hex(va), raw[off:off + 60].split(b'\0')[0])
    elif cmd == 'xref':
        for x in xrefs(int(sys.argv[2], 16)):
            print(hex(x))
    elif cmd == 'dis':
        print(dis(int(sys.argv[2], 16), int(sys.argv[3]) if len(sys.argv) > 3 else 60))
    elif cmd == 'calls':
        for x in calls_to(int(sys.argv[2], 16)):
            print(hex(x))
