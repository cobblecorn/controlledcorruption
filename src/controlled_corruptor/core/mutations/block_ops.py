"""Block-level mutation strategies: swap, repeat, shift.

These are coarse, experimental asset-corruption operations. They stay strictly
inside the effective mutable area by using the span picker for every region
they touch, so protected bytes are never involved.
"""

from __future__ import annotations

from typing import Optional

from ..history import MutationRecord
from .base import Mutation, MutationContext


def _block_size(ctx: MutationContext) -> int:
    base = max(1, ctx.settings.block_size)
    # Magnitude nudges the block size a little for variety.
    return max(1, round(base * (0.5 + ctx.settings.magnitude)))


class BlockSwap(Mutation):
    """Swap two non-overlapping same-size blocks."""

    name = "block_swap"

    def apply(self, ctx: MutationContext, index: int) -> Optional[MutationRecord]:
        size = _block_size(ctx)
        a = ctx.pick_span(size)
        b = ctx.pick_span(size)
        if a is None or b is None:
            return None
        if abs(a - b) < size:  # overlap -> skip to keep it clean
            return ctx.make_record(index, "block_swap", a, size=size, skipped=True,
                                   note="skipped: overlapping blocks")
        blk_a = bytes(ctx.out[a:a + size])
        blk_b = bytes(ctx.out[b:b + size])
        ctx.out[a:a + size] = blk_b
        ctx.out[b:b + size] = blk_a
        return ctx.make_record(index, "block_swap", a, size=size,
                               note=f"swap with 0x{b:08X} ({size}B)")


class BlockRepeat(Mutation):
    """Copy one block over another (duplicate nearby data)."""

    name = "block_repeat"

    def apply(self, ctx: MutationContext, index: int) -> Optional[MutationRecord]:
        size = _block_size(ctx)
        src = ctx.pick_span(size)
        dst = ctx.pick_span(size)
        if src is None or dst is None:
            return None
        if src == dst:
            return ctx.make_record(index, "block_repeat", dst, size=size, skipped=True,
                                   note="skipped: src == dst")
        ctx.out[dst:dst + size] = bytes(ctx.out[src:src + size])
        return ctx.make_record(index, "block_repeat", dst, size=size,
                               note=f"copied from 0x{src:08X} ({size}B)")


class BlockShift(Mutation):
    """Rotate the bytes within a window (move data around inside a region)."""

    name = "block_shift"

    def apply(self, ctx: MutationContext, index: int) -> Optional[MutationRecord]:
        window = _block_size(ctx) * 4
        off = ctx.pick_span(window)
        if off is None:
            # Fall back to a smaller window when regions are tight.
            window = _block_size(ctx)
            off = ctx.pick_span(window)
            if off is None:
                return None
        if window < 2:
            return None
        k = ctx.rng.randint(1, window - 1)
        buf = bytes(ctx.out[off:off + window])
        ctx.out[off:off + window] = buf[k:] + buf[:k]
        return ctx.make_record(index, "block_shift", off, size=window,
                               note=f"rotate {k}B in {window}B window")
