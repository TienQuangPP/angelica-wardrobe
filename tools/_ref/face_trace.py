"""Symbolic trace of a CECFace::Calculate* function (32-bit elementclient.exe).

Slider values are named after the factor field they use (CECFace + 0x148.. = Configs\\CustomizeFactor.ini order),
stack slots are followed through fstp / movss / xorps (negation) / constant stores, and every bone controller
call is printed with its vector argument resolved, e.g.  SCALE vec=(ScaleMouthH, 1, 1) mode=2 mark=1 mirror=1.

py face_trace.py <start hex> <end hex>
"""
import re
import sys

import pe

FACTORS = ("ScaleFaceH ScaleFaceV ScaleUpPart ScaleMiddlePart ScaleDownPart OffsetForeheadH OffsetForeheadV "
           "OffsetForeheadZ RotateForehead ScaleForehead OffsetYokeBoneH OffsetYokeBoneV OffsetYokeBoneZ RotateYokeBone "
           "ScaleYokeBone OffsetCheekH OffsetCheekV OffsetCheekZ ScaleCheek OffsetChainV OffsetChainZ RotateChain "
           "ScaleChainH OffsetJawH OffsetJawV OffsetJawZ ScaleJawSpecial ScaleJawH ScaleJawV ScaleEyeH ScaleEyeV "
           "RotateEye OffsetEyeH OffsetEyeV OffsetEyeZ ScaleEyeBall ScaleEyeH2 ScaleEyeV2 RotateEye2 OffsetEyeH2 "
           "OffsetEyeV2 OffsetEyeZ2 ScaleEyeBall2 ScaleBrowH ScaleBrowV RotateBrow OffsetBrowH OffsetBrowV OffsetBrowZ "
           "ScaleBrowH2 ScaleBrowV2 RotateBrow2 OffsetBrowH2 OffsetBrowV2 OffsetBrowZ2 ScaleNoseTipH ScaleNoseTipV "
           "OffsetNoseTipV ScaleNoseTipZ ScaleBridgeTipH OffsetBridgeTipZ ThickUpLip ThickDownLip ScaleMouthH "
           "OffsetMouthV OffsetMouthZ OffsetCornerOfMouthSpecial ScaleMouthH2 OffsetCornerOfMouthSpecial2 ScaleEar "
           "OffsetEarV").split()
FACTOR_AT = {0x148 + 4 * i: n for i, n in enumerate(FACTORS)}
OPS = {0x5efdb0: 'GROUP', 0x5efe80: 'PIVOT', 0x5ef350: 'SCALE', 0x5ef1b0: 'ROTATE', 0x5efec0: 'MOVE',
       0x5ef9c0: 'EYEBALL', 0x5eebf0: 'RIGHTSIDE', 0x5ecbf0: 'SHAPE', 0x5ee640: 'CLEAR', 0x5ef0d0: 'RESETSEL',
       0x5efd60: 'PART', 0x5ef180: 'RESETALL', 0x5ee530: 'ADDBONE', 0x5effe0: 'MARK'}
MAPS = {0xa367e0: 'scale', 0xa367a0: 'offset'}
NEG = 0x1373030

start, end = int(sys.argv[1], 16), int(sys.argv[2], 16)
off = pe.va2off(start)
slots: dict[int, str] = {}
xmm = {}
st0 = None
last_factor = None
last_field = None
regs: dict[str, object] = {}
pushes: list = []
second = False


def slot_of(op):
    m = re.search(r'\[ebp - (0x[0-9a-f]+|\d+)\]', op)
    return int(m.group(1), 0) if m else None


def vec(addr):
    return tuple(slots.get(addr - 4 * k, '?') for k in range(3))


def neg(s):
    return s[1:] if s.startswith('-') else '-' + s


for ins in pe.md.disasm(pe.raw[off:off + (end - start)], start):
    m, o = ins.mnemonic, ins.op_str
    a, _, b = o.partition(', ')
    if 'dword ptr [edi + 0x268]' in o or 'dword ptr [esi + 0x268]' in o:
        second = True  # the rest repeats the same on the second controller (other LOD)
    if second:
        break
    fm = re.search(r'\[e[sd]i \+ (0x[0-9a-f]+)\]', b or a)
    if m == 'movss' and fm and int(fm.group(1), 16) in FACTOR_AT and a.startswith('xmm'):
        last_factor = FACTOR_AT[int(fm.group(1), 16)]
        continue
    if m == 'movzx' and 'byte ptr [e' in b:
        last_field = b
        continue
    if m == 'call':
        try:
            t = int(o, 16)
        except ValueError:
            t = None
        if t in MAPS:
            st0 = last_factor or f'?{last_field}'
            last_factor = None
        elif t in OPS:
            name = OPS[t]
            args = list(reversed(pushes))
            desc = []
            for x in args:
                if isinstance(x, tuple):
                    desc.append('vec=(' + ', '.join(x) + ')')
                else:
                    desc.append(str(x))
            print(f'{ins.address:#x} {name:9s} ' + ' '.join(desc))
        pushes = []
        continue
    if m == 'fstp' and slot_of(a):
        slots[slot_of(a)] = st0 or '?'
        continue
    if m == 'movss':
        if a.startswith('xmm') and slot_of(b):
            xmm[a] = slots.get(slot_of(b), '?')
        elif slot_of(a) and b.startswith('xmm'):
            slots[slot_of(a)] = xmm.get(b, '?')
        continue
    if m == 'xorps' and hex(NEG) in b:
        xmm[a] = neg(xmm.get(a, '?'))
        continue
    if m == 'mov' and slot_of(a) and re.fullmatch(r'0x[0-9a-f]+|\d+', b):
        v = int(b, 0)
        slots[slot_of(a)] = {0: '0', 0x3f800000: '1', 0x80000000: '-0'}.get(v, hex(v))
        continue
    if m == 'mov' and re.fullmatch(r'e[a-d]x|e[sd]i', a) and re.fullmatch(r'0x[0-9a-f]+|\d+', b):
        regs[a] = int(b, 0)
        continue
    if m == 'lea' and slot_of(b):
        regs[a] = ('&', slot_of(b))
        continue
    if m == 'push':
        if re.fullmatch(r'0x[0-9a-f]+|\d+', o):
            pushes.append(int(o, 0))
        elif o in regs:
            r = regs[o]
            pushes.append(vec(r[1]) if isinstance(r, tuple) else r)
        else:
            pushes.append(o)
