"""Integer mutation strategies (16-bit and 32-bit).

Bytes are interpreted as signed/unsigned little/big-endian integers (the
region's endianness wins, otherwise the settings default) and adjusted by a
delta scaled by ``magnitude`` relative to the type's range.
"""

from __future__ import annotations

from typing import Optional

from ..history import MutationRecord
from .base import Mutation, MutationContext


class _IntMutation(Mutation):
    size = 2

    def apply(self, ctx: MutationContext, index: int) -> Optional[MutationRecord]:
        size = self.size
        off = ctx.pick_span(size)
        if off is None:
            return None
        region = ctx.lookup(off)
        endian = "little"
        if region and region.endianness:
            endian = region.endianness
        else:
            endian = ctx.settings.endianness
        signed = ctx.settings.signed

        old = ctx.read_int(off, size, endian, signed)
        # Delta up to +/- (magnitude * half the type's span).
        half_span = 1 << (size * 8 - 1)
        reach = max(1, round(ctx.settings.magnitude * half_span))
        delta = ctx.rng.randint(-reach, reach)
        new = old + delta
        ctx.write_int(off, size, new, endian)
        # Report the new value as re-read (reflects wrap into range).
        shown = ctx.read_int(off, size, endian, signed)
        return ctx.make_record(index, self.name, off, size=size,
                               before=str(old), after=str(shown),
                               note=f"{endian}/{'s' if signed else 'u'} delta={delta:+d}")


class Int16Mutation(_IntMutation):
    name = "int16"
    size = 2


class Int32Mutation(_IntMutation):
    name = "int32"
    size = 4
