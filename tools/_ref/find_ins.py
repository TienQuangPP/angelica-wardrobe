"""Find instructions in .text whose operand text matches a regex (linear sweep; good enough for MSVC code).

py find_ins.py <regex> [max hits]
"""
import re
import sys

import pe

pat = re.compile(sys.argv[1])
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 200
_, tva, tvs, tro, trs = pe.TEXT
pe.md.skipdata = True
hits = 0
for ins in pe.md.disasm(pe.raw[tro:tro + trs], tva):
    if pat.search(f"{ins.mnemonic} {ins.op_str}"):
        print(hex(ins.address), ins.mnemonic, ins.op_str, " func", hex(pe.find_func_start(ins.address) or 0))
        hits += 1
        if hits >= limit:
            break
