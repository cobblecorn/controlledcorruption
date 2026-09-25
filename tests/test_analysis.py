"""Hex viewer, value interpretation, search and heuristic analysis."""

from __future__ import annotations

import struct

from controlled_corruptor.core import analysis, hexview


def test_hex_dump_shape():
    data = bytes(range(32))
    dump = hexview.hex_dump(data, 0, 16)
    lines = dump.splitlines()
    assert lines[0].startswith("00000000  ")
    assert "|" in lines[0]
    assert len(lines) == 1  # 16 bytes, width 16


def test_hex_dump_base_offset_and_ascii():
    data = b"ABCD" + bytes([0, 1, 2])
    dump = hexview.hex_dump(data, 0, 7, base_offset=0x1000)
    assert dump.startswith("00001000  ")
    assert "|ABCD" in dump


def test_interpret_types():
    data = struct.pack("<i", -5) + struct.pack("<f", 1.5)
    info = hexview.interpret(data, 0, endian="little")
    assert info["int32"] == -5
    assert "float32" in info and "pointer" in info  # keys present
    info2 = hexview.interpret(data, 4, endian="little")
    assert abs(info2["float32"] - 1.5) < 1e-6


def test_search_bytes():
    data = b"xx\xde\xad\xbe\xefyy\xde\xad"
    assert analysis.search_bytes(data, b"\xde\xad") == [2, 8]


def test_search_int_roundtrip():
    data = struct.pack("<I", 0) + struct.pack("<I", 0xCAFEBABE) + struct.pack("<I", 0)
    hits = analysis.search_int(data, 0xCAFEBABE, size=4, endian="little")
    assert 4 in hits


def test_search_float_tolerance():
    data = struct.pack("<f", 3.14159) + struct.pack("<f", 100.0)
    hits = analysis.search_float(data, 3.1416, tol=1e-2, endian="little")
    assert 0 in hits
    assert analysis.search_float(data, 999.0, tol=1e-3) == []


def test_find_strings():
    data = b"\x00\x01Hello, world!\x00\x02ab"
    found = analysis.find_strings(data, min_len=4)
    assert any(f.text.startswith("Hello") for f in found)
    # "ab" too short to appear at min_len 4
    assert all(len(f.text) >= 4 for f in found)


def test_entropy_zero_for_constant_and_high_for_random():
    zeros = bytes(4096)
    pairs = analysis.entropy_blocks(zeros, blocks=4)
    assert all(e == 0.0 for _o, e in pairs)

    import os
    rnd = os.urandom(4096)
    pr = analysis.entropy_blocks(rnd, blocks=4)
    assert all(e > 6.5 for _o, e in pr)  # random bytes ~ 8 bits


def test_entropy_sparkline_length():
    pairs = [(0, 0.0), (1, 4.0), (2, 8.0)]
    spark = analysis.entropy_sparkline(pairs)
    assert len(spark) == 3


def test_pointer_candidates():
    # a word equal to a valid in-file offset should be flagged
    data = struct.pack("<I", 0x10) + bytes(0x20)
    cands = analysis.pointer_candidates(data, size=4, endian="little")
    assert (0, 0x10) in cands


def test_float_triplets_detects_vertex_run():
    buf = bytearray()
    for i in range(8):
        for k in range(3):
            buf += struct.pack("<f", float(i * 3 + k))
    runs = analysis.float_triplets(bytes(buf), endian="little", min_run=4)
    assert runs and runs[0][0] == 0 and runs[0][1] >= 4
