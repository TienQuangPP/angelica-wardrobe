"""Parser for Angelica skeleton animation tracks (.stck, magic MOXBKCTS).

Layout: magic[8], version, numTracks, startFrame, endFrame, frameRate, then per bone:
    int boneId,
    position track: int numKeys, int numSegments, int frameRate, float3 keys[numKeys], segments[numSegments],
    rotation track: int numKeys, int numSegments, int frameRate, float4 keys[numKeys] (x, y, z, w), segments[...]
A segment is (startTime ms, endTime ms, startKey, endKey). Keys are the bone's transform relative to its parent.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

import numpy as np


@dataclass
class Track:
    bone: int
    fps: int
    pos: np.ndarray  # (n, 3)
    rot: np.ndarray  # (m, 4) quaternion x, y, z, w
    pos_times: np.ndarray  # seconds
    rot_times: np.ndarray


@dataclass
class Animation:
    start: int
    end: int
    fps: int
    tracks: list[Track]

    @property
    def duration(self) -> float:
        return max(0.0, (self.end - self.start) / max(self.fps, 1))


def _read_track(data: bytes, pos: int, width: int):
    n, nseg, fps = struct.unpack_from("<3i", data, pos)
    pos += 12
    if not (0 <= n < 100000 and 0 <= nseg < 10000 and 0 < fps <= 1000):
        raise ValueError(f"bad track header {n} {nseg} {fps}")
    keys = np.frombuffer(data, "<f4", n * width, pos).reshape(n, width).astype(np.float64)
    pos += n * width * 4
    segs = struct.unpack_from(f"<{4 * nseg}i", data, pos) if nseg else ()
    pos += 16 * nseg
    # key times: segments map key ranges onto time ranges; without segments keys run at fps
    times = np.arange(n, dtype=np.float64) / fps
    for i in range(nseg):
        t0, t1, k0, k1 = segs[4 * i: 4 * i + 4]
        if 0 <= k0 < n and k0 <= k1 < n:
            count = k1 - k0
            times[k0:k1 + 1] = np.linspace(t0, t1, count + 1) / 1000.0 if count else t0 / 1000.0
    return keys, times, fps, pos


def _read_track_v2(data: bytes, pos: int, rotation: bool):
    """Version 2: keys may drop the quaternion's w, and key times come from a uint16 frame table."""
    n, _nseg, fps = struct.unpack_from("<3i", data, pos)
    pos += 12
    if not (0 <= n < 100000 and 0 < fps <= 1000):
        raise ValueError(f"bad v2 track header {n} {fps}")
    width = 3
    if rotation:
        (mode,) = struct.unpack_from("<i", data, pos)
        pos += 4
        width = 3 if mode == 1 else 4
    keys = np.frombuffer(data, "<f4", n * width, pos).reshape(n, width).astype(np.float64)
    pos += n * width * 4
    if rotation and width == 3:  # rebuild w (stored quaternions keep w >= 0)
        w = np.sqrt(np.clip(1 - (keys ** 2).sum(1), 0, 1))
        keys = np.c_[keys, w]
    pos += 8  # total time in ms, segment count
    frames = np.frombuffer(data, "<u2", n, pos).astype(np.float64)
    pos += 2 * n
    return keys, frames / fps, fps, pos


def parse_stck(data: bytes) -> Animation:
    if data[:8] != b"MOXBKCTS":
        raise ValueError("not a STCK file")
    version, count, start, end, fps = struct.unpack_from("<5i", data, 8)
    pos = 28
    tracks = []
    for _ in range(count):
        (bone,) = struct.unpack_from("<i", data, pos)
        pos += 4
        if version >= 2:
            p, pt, f, pos = _read_track_v2(data, pos, False)
            r, rt, _, pos = _read_track_v2(data, pos, True)
        else:
            p, pt, f, pos = _read_track(data, pos, 3)
            r, rt, _, pos = _read_track(data, pos, 4)
        tracks.append(Track(bone, f, p, r, pt, rt))
    if pos != len(data):
        raise ValueError(f"{len(data) - pos} trailing bytes")
    return Animation(start, end, fps, tracks)
