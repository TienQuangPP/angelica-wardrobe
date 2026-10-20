"""Condensed view of CECFace::Calculate* functions: customize fields, factor fields, constants and the bone
controller calls (group select 0x5efdb0, pivot 0x5efe80, transform 0x5ef350, reset 0x5ee640).

py face_calls.py <func va hex> [...]
"""
import struct
import sys

import pe

NAMES = {0x5efdb0: 'GROUP', 0x5efe80: 'PIVOT', 0x5ef350: 'XFORM', 0x5ee640: 'RESET', 0xa367e0: 'SCALEMAP',
         0x5effe0: 'MARK', 0x5ee530: 'ADDBONE'}


def fl(v):
    return struct.unpack('<f', struct.pack('<I', v & 0xffffffff))[0]


args = [int(a, 16) for a in sys.argv[1:]]
for n, va in enumerate(args):
    end = args[n + 1] if n + 1 < len(args) and args[n + 1] > va else va + 12000
    off = pe.va2off(va)
    print(f'===== {va:#x}')
    for ins in pe.md.disasm(pe.raw[off:off + (end - va)], va):
        m, o = ins.mnemonic, ins.op_str
        keep = False
        note = ''
        if m == 'call':
            try:
                t = int(o, 16)
                note = NAMES.get(t, f'call {t:#x}')
            except ValueError:
                note = 'call ' + o
            keep = True
        elif m == 'push' and o.startswith('0x'):
            v = int(o, 16)
            note = f'push {v:#x} ({fl(v):.4g})' if v > 0x1000 else f'push {v}'
            keep = True
        elif m == 'push' and o in ('0', '1', '2', '3', '4', '5', '6', '7', '8', '9'):
            note = f'push {o}'
            keep = True
        elif 'byte ptr [esi + 0x' in o or 'byte ptr [edi + 0x' in o or 'word ptr [esi + 0x' in o:
            keep = True
        elif ('dword ptr [esi + 0x1' in o or 'dword ptr [esi + 0x2' in o or 'dword ptr [edi + 0x1' in o
              or 'dword ptr [edi + 0x2' in o) and m in ('movss', 'mulss', 'addss', 'subss'):
            keep = True
        elif m == 'mov' and 'ptr [esp' in o and ', 0x' in o:
            v = int(o.split(', ')[1], 16)
            note = f'{o}  ({fl(v):.4g})'
            keep = True
        elif m in ('mov', 'movss') and ('[0x1' in o):
            o2 = o.split('[0x')[1].split(']')[0]
            a = int(o2, 16)
            b = pe.raw[pe.va2off(a):pe.va2off(a) + 4] if pe.va2off(a) else b''
            b = b if len(b) == 4 else b'\0\0\0\0'
            note = f'{o}  (={struct.unpack("<f", b)[0]:.4g})'
            keep = True
        elif m in ('ret',):
            print(f'  {ins.address:#x} ret')
            continue
        if keep:
            print(f'  {ins.address:#x} {m} {o}' + (f'   <- {note}' if note else ''))
