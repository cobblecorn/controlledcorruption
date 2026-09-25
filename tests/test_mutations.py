"""Behavioural tests for individual mutation strategies and helpers."""

from __future__ import annotations

import math
import struct

from controlled_corruptor.core import mutations as mut
from controlled_corruptor.core.engine import _SpanPicker
from controlled_corruptor.core.mutations.base import MutationContext
from controlled_corruptor.core.prng import Rng
from controlled_corruptor.core.settings import MutationSettings


def _ctx(data: bytes, intervals, settings=None):
    out = bytearray(data)
    rng = Rng("mut-test")
    settings = settings or MutationSettings(seed="mut-test", magnitude=0.5)
    picker = _SpanPicker(intervals, rng)
    return MutationContext(out=out, rng=rng, settings=settings,
                           pick_span=picker.pick, lookup=lambda _o: None)


def test_registry_has_all_types():
    names = set(mut.available())
    assert {"byte_replace", "bit_flip", "byte_offset", "int16", "int32",
            "float32", "block_swap", "block_repeat", "block_shift"} <= names


def test_byte_replace_changes_one_byte():
    ctx = _ctx(bytes(64), [(0, 64)])
    rec = mut.get("byte_replace").apply(ctx, 0)
    diffs = [i for i in range(64) if ctx.out[i] != 0]
    assert len(diffs) == 1
    assert rec.offset == diffs[0]


def test_bit_flip_only_flips_bits():
    data = bytes([0b10101010] * 32)
    ctx = _ctx(data, [(0, 32)])
    rec = mut.get("bit_flip").apply(ctx, 0)
    # only one byte changed and only via XOR (same popcount distance)
    changed = [i for i in range(32) if ctx.out[i] != data[i]]
    assert len(changed) == 1
    old, new = data[changed[0]], ctx.out[changed[0]]
    assert (old ^ new) != 0


def test_byte_offset_clamp_mode_stays_in_range():
    settings = MutationSettings(seed=1, magnitude=1.0, wrap=False)
    for _ in range(50):
        ctx = _ctx(bytes([250] * 8), [(0, 8)], settings)
        mut.get("byte_offset").apply(ctx, 0)
        assert all(0 <= b <= 255 for b in ctx.out)


def test_float32_never_produces_nan_by_default():
    # data full of large finite floats
    buf = bytearray()
    for _ in range(64):
        buf += struct.pack(">f", 3.0e38)
    settings = MutationSettings(seed=2, magnitude=1.0, allow_nan=False,
                                types=["float32"], endianness="big")
    for i in range(200):
        ctx = _ctx(bytes(buf), [(0, len(buf))], settings)
        mut.get("float32").apply(ctx, i)
        vals = struct.unpack(">" + "f" * (len(buf) // 4), bytes(ctx.out))
        assert all(math.isfinite(v) for v in vals)


def test_int16_endianness_roundtrip():
    data = struct.pack(">h", 1000) + bytes(30)
    settings = MutationSettings(seed=3, magnitude=0.1, endianness="big", signed=True)
    ctx = _ctx(data, [(0, 2)], settings)
    rec = mut.get("int16").apply(ctx, 0)
    assert rec.operation == "int16"
    assert rec.before == "1000"


def test_block_swap_preserves_multiset_of_bytes():
    data = bytes(range(128))
    settings = MutationSettings(seed=4, magnitude=0.2, block_size=8)
    ctx = _ctx(data, [(0, 128)], settings)
    mut.get("block_swap").apply(ctx, 0)
    assert sorted(ctx.out) == sorted(data)  # swap only rearranges bytes


def test_span_picker_never_exceeds_interval():
    rng = Rng(9)
    picker = _SpanPicker([(10, 20), (100, 104)], rng)
    for _ in range(500):
        off = picker.pick(4)
        if off is None:
            continue
        assert (10 <= off and off + 4 <= 20) or (100 <= off and off + 4 <= 104)


def test_span_picker_returns_none_when_too_big():
    rng = Rng(9)
    picker = _SpanPicker([(0, 4)], rng)
    assert picker.pick(8) is None
