"""Write the main icon group of a Windows exe (all sizes) as a .ico file.

py exe_icon.py <exe> <out.ico>
"""
import struct
import sys

import pefile

pe = pefile.PE(sys.argv[1])
RT_ICON, RT_GROUP_ICON = 3, 14
icons, groups = {}, []
for typ in pe.DIRECTORY_ENTRY_RESOURCE.entries:
    for name in typ.directory.entries:
        for lang in name.directory.entries:
            data = pe.get_data(lang.data.struct.OffsetToData, lang.data.struct.Size)
            if typ.id == RT_ICON:
                icons[name.id] = data
            elif typ.id == RT_GROUP_ICON:
                groups.append(data)
if not groups:
    sys.exit("no icon group")
grp = groups[0]
_, _, count = struct.unpack_from("<HHH", grp, 0)
entries = []
for i in range(count):
    w, h, colors, _, planes, bits, size, rid = struct.unpack_from("<BBBBHHIH", grp, 6 + i * 14)
    entries.append((w, h, colors, planes, bits, icons[rid]))
out = bytearray(struct.pack("<HHH", 0, 1, len(entries)))
offset = 6 + 16 * len(entries)
for w, h, colors, planes, bits, data in entries:
    out += struct.pack("<BBBBHHII", w, h, colors, 0, planes, bits, len(data), offset)
    offset += len(data)
for e in entries:
    out += e[5]
open(sys.argv[2], "wb").write(out)
print("icon sizes:", [(e[0] or 256, e[1] or 256) for e in entries])
