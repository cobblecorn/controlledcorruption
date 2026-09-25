"""Byte-level mutation strategies: replace, bit flip, signed offset."""

from __future__ import annotations

from typing import Optional

from ..history import MutationRecord
from .base import Mutation, MutationContext


class ByteReplace(Mutation):
    """Replace a single byte with a fresh random value (guaranteed to differ)."""

    name = "byte_replace"

    def apply(self, ctx: MutationContext, index: int) -> Optional[MutationRecord]:
        off = ctx.pick_span(1)
        if off is None:
            return None
        old = ctx.out[off]
        new = ctx.rng.randint(0, 255)
        if new == old:
            new = (new + 1) & 0xFF
        ctx.out[off] = new
        return ctx.make_record(index, "byte_replace", off, size=1,
                               before=str(old), after=str(new))


class BitFlip(Mutation):
    """Flip N distinct bits in a byte; N scales with magnitude (1..8)."""

    name = "bit_flip"

    def apply(self, ctx: MutationContext, index: int) -> Optional[MutationRecord]:
        off = ctx.pick_span(1)
        if off is None:
            return None
        bits = max(1, min(8, round(ctx.settings.magnitude * 8)))
        mask = ctx.rng.sample_bits(bits, 8)
        old = ctx.out[off]
        new = old ^ mask
        ctx.out[off] = new
        return ctx.make_record(index, "bit_flip", off, size=1,
                               before=f"{old:08b}", after=f"{new:08b}",
                               note=f"mask={mask:08b}")


class ByteOffset(Mutation):
    """Add a signed delta to a byte; wrap or clamp per settings."""

    name = "byte_offset"

    def apply(self, ctx: MutationContext, index: int) -> Optional[MutationRecord]:
        off = ctx.pick_span(1)
        if off is None:
            return None
        reach = max(1, round(ctx.settings.magnitude * 128))
        delta = ctx.rng.randint(-reach, reach)
        old = ctx.out[off]
        raw = old + delta
        note = ""
        if ctx.settings.wrap:
            new = raw & 0xFF
        else:
            new = max(0, min(255, raw))
            if new != raw:
                note = "clamped"
        ctx.out[off] = new
        return ctx.make_record(index, "byte_offset", off, size=1,
                               before=str(old), after=str(new),
                               note=(note or f"delta={delta:+d}"))
