"""Reader for Angelica File Package (.pck/.pkx/.pkx1) archives, version 0x00020003.

Large packages are split into .pck + .pkx + .pkx1 parts; offsets address the
concatenation of all parts and the index tail lives at the end of the last one.
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

KEY1 = 0xA8937462
KEY2 = 0xF1A43653
GUARD1 = 0xFDFDFEEE
GUARD2 = 0xF00DBEEF
TAIL_SIZE = 288
PATH_LEN = 260


@dataclass
class Entry:
    path: str
    offset: int
    size: int
    csize: int


class MultiPartFile:
    def __init__(self, parts: list[Path]):
        self.parts = parts
        self.sizes = [p.stat().st_size for p in parts]
        self.handles = [open(p, "rb") for p in parts]
        self.total = sum(self.sizes)

    def read(self, offset: int, length: int) -> bytes:
        out = bytearray()
        base = 0
        for size, fh in zip(self.sizes, self.handles):
            if length <= 0:
                break
            if offset < base + size:
                local = offset - base
                n = min(length, size - local)
                fh.seek(local)
                out += fh.read(n)
                offset += n
                length -= n
            base += size
        return bytes(out)

    def close(self) -> None:
        for fh in self.handles:
            fh.close()


def package_parts(pck: Path) -> list[Path]:
    parts = [pck]
    for ext in (".pkx", ".pkx1", ".pkx2", ".pkx3"):
        nxt = pck.with_suffix(ext)
        if not nxt.exists():
            break
        parts.append(nxt)
    return parts


class Package:
    def __init__(self, pck: Path | str):
        self.pck = Path(pck)
        self.data = MultiPartFile(package_parts(self.pck))
        self.entries = self._read_index()

    def _read_index(self) -> list[Entry]:
        tail = self.data.read(self.data.total - TAIL_SIZE, TAIL_SIZE)
        guard1, version, table_off, _flags = struct.unpack_from("<IIQI", tail, 0)
        guard2, _zero, count, version2 = struct.unpack_from("<IIII", tail, TAIL_SIZE - 16)
        if guard1 != GUARD1 or guard2 != GUARD2 or version != 0x00020003 or version2 != version:
            raise ValueError(f"{self.pck.name}: unsupported package tail")
        table_off ^= KEY1 | 0xFFFFFFFF00000000
        table = self.data.read(table_off, self.data.total - TAIL_SIZE - table_off)

        entries: list[Entry] = []
        pos = 0
        for _ in range(count):
            a, b = struct.unpack_from("<II", table, pos)
            pos += 8
            size = a ^ KEY1
            if size != b ^ KEY2:
                raise ValueError(f"{self.pck.name}: corrupt index at {pos}")
            raw = table[pos:pos + size]
            pos += size
            try:
                raw = zlib.decompress(raw)
            except zlib.error:
                pass
            name = raw[:PATH_LEN].split(b"\0", 1)[0].decode("gbk", errors="replace")
            offset, fsize, csize = struct.unpack_from("<QII", raw, 264)
            entries.append(Entry(name, offset, fsize, csize))
        return entries

    def read(self, entry: Entry) -> bytes:
        raw = self.data.read(entry.offset, entry.csize)
        if entry.csize < entry.size:
            raw = zlib.decompress(raw)
        return raw

    def close(self) -> None:
        self.data.close()
