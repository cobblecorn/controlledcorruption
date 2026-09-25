"""Semantic texture corruption: channel ops and palette ops."""

from __future__ import annotations

import struct

from controlled_corruptor.core import texture


def _rgba(pixels):
    buf = bytearray()
    for r, g, b, a in pixels:
        buf += bytes([r, g, b, a])
    return buf


def test_channel_swap_rgba():
    buf = _rgba([(10, 20, 30, 40), (1, 2, 3, 4)])
    fmt = texture.get_format("rgba8888")
    s = texture.TextureSettings(op="channel_swap", channel_a=0, channel_b=2)
    texture.corrupt_texture(buf, 0, len(buf), fmt, s)
    # R and B swapped, G and A intact
    assert list(buf[0:4]) == [30, 20, 10, 40]
    assert list(buf[4:8]) == [3, 2, 1, 4]


def test_invert_alpha_only():
    buf = _rgba([(10, 20, 30, 40)])
    fmt = texture.get_format("rgba8888")
    s = texture.TextureSettings(op="invert", channel=3)
    texture.corrupt_texture(buf, 0, len(buf), fmt, s)
    assert list(buf[0:4]) == [10, 20, 30, 215]  # 255-40


def test_channel_scale_clamps():
    buf = _rgba([(200, 200, 200, 200)])
    fmt = texture.get_format("rgba8888")
    s = texture.TextureSettings(op="channel_scale", strength=1.0)  # x2 -> clamp 255
    texture.corrupt_texture(buf, 0, len(buf), fmt, s)
    assert list(buf[0:4]) == [255, 255, 255, 255]


def test_channel_shift_deterministic_and_bounded():
    fmt = texture.get_format("rgba8888")
    a = _rgba([(100, 100, 100, 100)] * 8)
    b = bytearray(a)
    s = texture.TextureSettings(op="channel_shift", strength=0.5, seed="x")
    texture.corrupt_texture(a, 0, len(a), fmt, texture.TextureSettings(
        op="channel_shift", strength=0.5, seed="x"))
    texture.corrupt_texture(b, 0, len(b), fmt, s)
    assert bytes(a) == bytes(b)  # deterministic
    assert all(0 <= v <= 255 for v in a)  # bounded


def test_rgba5551_packed_roundtrip():
    fmt = texture.get_format("rgba5551", endian="big")
    # encode a known pixel then swap R/B
    buf = bytearray(2)
    fmt.encode(buf, 0, [31, 0, 0, 1])   # full red, alpha on
    assert fmt.decode(bytes(buf), 0) == [31, 0, 0, 1]
    s = texture.TextureSettings(op="channel_swap", channel_a=0, channel_b=2)
    texture.corrupt_texture(buf, 0, len(buf), fmt, s)
    assert fmt.decode(bytes(buf), 0) == [0, 0, 31, 1]  # red moved to blue


def test_palette_rotate():
    # 4 palette entries of 2 bytes
    buf = bytearray(struct.pack(">4H", 0x1111, 0x2222, 0x3333, 0x4444))
    s = texture.TextureSettings(op="palette_rotate", rotate_by=1, entry_size=2)
    texture.corrupt_texture(buf, 0, len(buf), None, s)
    assert struct.unpack(">4H", bytes(buf)) == (0x2222, 0x3333, 0x4444, 0x1111)


def test_palette_shuffle_is_permutation_and_deterministic():
    original = struct.pack(">8H", *range(1, 9))
    a = bytearray(original)
    b = bytearray(original)
    s = texture.TextureSettings(op="palette_shuffle", entry_size=2, seed="pal")
    texture.corrupt_texture(a, 0, len(a), None, texture.TextureSettings(
        op="palette_shuffle", entry_size=2, seed="pal"))
    texture.corrupt_texture(b, 0, len(b), None, s)
    assert bytes(a) == bytes(b)                      # deterministic
    assert sorted(struct.unpack(">8H", bytes(a))) == list(range(1, 9))  # permutation
    assert bytes(a) != original                       # actually changed


def test_only_region_touched():
    buf = bytearray(_rgba([(1, 2, 3, 4)] * 10))
    original = bytes(buf)
    fmt = texture.get_format("rgba8888")
    s = texture.TextureSettings(op="invert")
    texture.corrupt_texture(buf, 8, 24, fmt, s)  # pixels 2..5
    assert buf[:8] == original[:8]
    assert buf[24:] == original[24:]
