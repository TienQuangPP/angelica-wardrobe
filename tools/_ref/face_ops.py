"""List the bone controller operations of CECFace functions with their arguments.

For every call to the controller (group, pivot, translate, rotate, scale, eyeball, right side, shape) print the
pushes before it (register pushes resolved from the nearest 'mov reg, imm' / 'push imm') and the lea'd vector.
py face_ops.py <start hex> <end hex>
"""
import re
import sys

import pe

OPS = {0x5efdb0: 'GROUP', 0x5efe80: 'PIVOT', 0x5ef350: 'SCALE', 0x5ef1b0: 'ROTATE', 0x5efec0: 'MOVE',
       0x5ef9c0: 'EYEBALL', 0x5eebf0: 'RIGHTSIDE', 0x5ecbf0: 'SHAPE', 0x5ee640: 'CLEAR', 0x5ef0d0: 'RESETSEL',
       0x5efd60: 'PART', 0x5ef180: 'RESETALL', 0x5ee530: 'ADDBONE'}

start, end = int(sys.argv[1], 16), int(sys.argv[2], 16)
off = pe.va2off(start)
ins_list = list(pe.md.disasm(pe.raw[off:off + (end - start)], start))
regs = {}
pending = []
for ins in ins_list:
    m, o = ins.mnemonic, ins.op_str
    if m == 'mov' and re.fullmatch(r'e[a-d]x|e[sd]i', o.split(',')[0]) and re.fullmatch(r'0x[0-9a-f]+|\d+', o.split(', ')[1] if ', ' in o else ''):
        regs[o.split(',')[0]] = int(o.split(', ')[1], 0)
    if m in ('xor',) and o.split(', ')[0] == o.split(', ')[-1]:
        regs[o.split(',')[0]] = 0
    if m == 'push':
        if re.fullmatch(r'0x[0-9a-f]+|\d+', o):
            pending.append(str(int(o, 0)))
        elif o in regs:
            pending.append(f'{o}={regs[o]}')
        else:
            pending.append(o)
    if m == 'lea' and 'ebp -' in o:
        pending.append('&' + o.split('[')[1].rstrip(']').replace('ebp - ', 'v'))
    if m == 'call':
        try:
            t = int(o, 16)
        except ValueError:
            t = None
        name = OPS.get(t)
        if name:
            print(f'{ins.address:#x} {name:9s} args(last pushed first): {list(reversed(pending[-6:]))}')
        pending = []
