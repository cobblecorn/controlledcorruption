"""Semantic (Level-3) vertex/float-array corruption."""

from __future__ import annotations

import math
import struct

from controlled_corruptor.core import semantic


def _vertices(triplets, endian="little"):
    e = "<" if endian == "little" else ">"
    buf = bytearray()
    for x, y, z in triplets:
        buf += struct.pack(e + "fff", x, y, z)
    return buf


def _read(buf, endian="little"):
    e = "<" if endian == "little" else ">"
    n = len(buf) // 4
    return list(struct.unpack(e + "f" * n, bytes(buf)))


def test_scale_only_selected_axis():
    buf = _vertices([(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)])
    layout = semantic.build_layout(stride=12, endian="little")
    s = semantic.SemanticSettings(op="scale", strengths=[0.0, 1.0, 0.0], seed=1)
    semantic.corrupt_region(buf, 0, len(buf), layout, s)
    vals = _read(buf)
    # X and Z unchanged, Y doubled (scale by 1+1.0)
    assert vals[0] == 1.0 and vals[2] == 3.0
    assert abs(vals[1] - 4.0) < 1e-6   # 2.0 * 2
    assert abs(vals[4] - 10.0) < 1e-6  # 5.0 * 2


def test_mirror_negates_axis():
    buf = _vertices([(1.0, 2.0, 3.0)])
    layout = semantic.build_layout(stride=12)
    s = semantic.SemanticSettings(op="mirror", strengths=[1.0, 0.0, 0.0], seed=1)
    semantic.corrupt_region(buf, 0, len(buf), layout, s)
    vals = _read(buf)
    assert vals[0] == -1.0 and vals[1] == 2.0 and vals[2] == 3.0


def test_flatten_zeros_axis():
    buf = _vertices([(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)])
    layout = semantic.build_layout(stride=12)
    s = semantic.SemanticSettings(op="flatten", strengths=[0.0, 0.0, 1.0], seed=1)
    semantic.corrupt_region(buf, 0, len(buf), layout, s)
    vals = _read(buf)
    assert vals[2] == 0.0 and vals[5] == 0.0
    assert vals[0] == 1.0 and vals[4] == 5.0


def test_preserves_topology_extra_stride_bytes():
    # 16-byte elements: xyz floats + a 4-byte "index" that must NOT change
    e = "<"
    buf = bytearray()
    for i in range(4):
        buf += struct.pack(e + "fff", float(i), float(i), float(i))
        buf += struct.pack(e + "I", 0xAABBCCDD)  # index/connectivity
    original = bytes(buf)
    layout = semantic.build_layout(stride=16, component_offsets=(0, 4, 8))
    s = semantic.SemanticSettings(op="scale", strengths=[2.0, 2.0, 2.0], seed=1)
    semantic.corrupt_region(buf, 0, len(buf), layout, s)
    # every index word is intact
    for i in range(4):
        off = i * 16 + 12
        assert buf[off:off + 4] == original[off:off + 4]


def test_avoid_nan_keeps_finite():
    buf = _vertices([(3.0e38, 3.0e38, 3.0e38)])
    layout = semantic.build_layout(stride=12)
    s = semantic.SemanticSettings(op="stretch", strengths=[1.0, 1.0, 1.0],
                                  avoid_nan=True, seed=1)
    semantic.corrupt_region(buf, 0, len(buf), layout, s)
    assert all(math.isfinite(v) for v in _read(buf))


def test_reverse_reverses_component_sequence():
    buf = _vertices([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0)])
    layout = semantic.build_layout(stride=12)
    s = semantic.SemanticSettings(op="reverse", strengths=[1.0, 0.0, 0.0], seed=1)
    semantic.corrupt_region(buf, 0, len(buf), layout, s)
    xs = [_read(buf)[i * 3] for i in range(3)]
    assert xs == [2.0, 1.0, 0.0]


def test_determinism():
    buf1 = _vertices([(float(i), float(i + 1), float(i + 2)) for i in range(20)])
    buf2 = bytes(buf1)
    b1 = bytearray(buf1)
    b2 = bytearray(buf2)
    layout = semantic.build_layout(stride=12)
    s = semantic.SemanticSettings(op="displace", strengths=[0.4, 2.0, 0.2], seed="cody")
    semantic.corrupt_region(b1, 0, len(b1), layout, semantic.SemanticSettings(
        op="displace", strengths=[0.4, 2.0, 0.2], seed="cody"))
    semantic.corrupt_region(b2, 0, len(b2), layout, s)
    assert bytes(b1) == bytes(b2)


def test_only_region_changes():
    buf = bytearray(_vertices([(float(i),) * 3 for i in range(10)]))
    original = bytes(buf)
    layout = semantic.build_layout(stride=12)
    s = semantic.SemanticSettings(op="scale", strengths=[1.0, 1.0, 1.0], seed=1)
    # only corrupt elements 2..5
    semantic.corrupt_region(buf, 24, 72, layout, s)
    assert buf[:24] == original[:24]
    assert buf[72:] == original[72:]
    assert buf[24:72] != original[24:72]
