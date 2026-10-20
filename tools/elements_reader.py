"""Reader for this client's element\\data\\elements.data (version 0x30000213).

Layout (from elementclient.exe, elementdataman loader at 0x5def80):
    uint32 version (0x30000213), uint32 timestamp
    uint32 n, n raw bytes            (extra data block, unused here)
    uint32 x, uint32 len, char[len], uint32 timestamp2, uint32 y, uint32 len, char[len]
    then the lists, in order; most lists are:
        uint32 count, count x (uint32 id, uint16 size), uint32 total, total bytes of records
    every record is compressed on its own with MPPC (RFC 2118, 8 KB history) -> struct of the list's size.
The per-list struct sizes are pushed by the elementdataman constructor (0x5c6a60): see SIZES below.
"""
from __future__ import annotations

import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tghm_paths import ELEMENT  # noqa: E402

ELEMENTS = str(ELEMENT / "data" / "elements.data")


def mppc_decompress(src: bytes, limit: int = 1 << 20) -> bytes:
    """RFC 2118 MPPC decoder (bit stream MSB first), as in elementclient.exe 0x5df750."""
    n_bits = len(src) * 8
    val = int.from_bytes(src, "big")
    pos = 0
    out = bytearray()

    def bits(k: int) -> int:
        nonlocal pos
        if pos + k > n_bits:
            raise EOFError
        v = (val >> (n_bits - pos - k)) & ((1 << k) - 1)
        pos += k
        return v

    try:
        while n_bits - pos >= 8 and len(out) < limit:
            if bits(1) == 0:  # 0xxxxxxx literal < 0x80
                out.append(bits(7))
                continue
            if bits(1) == 0:  # 10xxxxxxx literal >= 0x80
                out.append(0x80 | bits(7))
                continue
            # copy tuple: 1111 + 6 bits | 1110 + 8 bits | 110 + 13 bits
            if bits(1) == 0:
                off = bits(13) + 320
            elif bits(1) == 0:
                off = bits(8) + 64
            else:
                off = bits(6)
            # length: 0 -> 3, 10x{2} -> 4..7, 110x{3} -> 8..15, ... (k ones, a zero, k+1 bits)
            k = 0
            while bits(1) == 1:
                k += 1
                if k > 11:
                    raise ValueError("bad length")
            length = 3 if k == 0 else (1 << (k + 1)) + bits(k + 1)
            start = len(out) - off
            if off == 0 or start < 0:
                raise ValueError(f"bad offset {off}")
            for i in range(length):
                out.append(out[start + i])
    except EOFError:
        pass
    return bytes(out)


@dataclass
class ElementList:
    index: int
    offset: int
    ids: list = field(default_factory=list)
    sizes: list = field(default_factory=list)
    data_offset: int = 0
    end: int = 0

    def records(self, data: bytes):
        p = self.data_offset
        for rid, size in zip(self.ids, self.sizes):
            yield rid, data[p:p + size]
            p += size


def read_lists(data: bytes, max_lists: int = 400):
    """Walk the standard lists from the start of the list area; stops at the first non-standard list."""
    p = 8
    n = struct.unpack_from("<I", data, p)[0]
    p += 4 + n
    p += 4
    ln = struct.unpack_from("<I", data, p)[0]
    p += 4 + ln + 4 + 4
    ln = struct.unpack_from("<I", data, p)[0]
    p += 4 + ln
    lists = []
    for idx in range(max_lists):
        if p + 4 > len(data):
            break
        count = struct.unpack_from("<I", data, p)[0]
        if count > 2_000_000:
            break
        lst = ElementList(idx, p)
        q = p + 4
        if count == 0:  # empty lists stop right after the count
            lst.data_offset = lst.end = q
            lists.append(lst)
            p = q
            continue
        for i in range(count):
            rid, size = struct.unpack_from("<IH", data, q)
            lst.ids.append(rid)
            lst.sizes.append(size)
            q += 6
        total = struct.unpack_from("<I", data, q)[0]
        if total != sum(lst.sizes):
            lst.end = -1
            lists.append(lst)
            break
        lst.data_offset = q + 4
        lst.end = lst.data_offset + total
        lists.append(lst)
        p = lst.end
    return lists


if __name__ == "__main__":
    import sys
    data = open(ELEMENTS, "rb").read()
    lists = read_lists(data)
    for l in lists:
        first = next(l.records(data), (None, b""))
        dec = mppc_decompress(first[1]) if first[0] is not None else b""
        print(l.index, hex(l.offset), len(l.ids), "end" if l.end > 0 else "STOP", len(dec), dec[:40].hex(" "))
