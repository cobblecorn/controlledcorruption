"""Float32 mutation strategy.

Useful for positions, scale, rotations, animation values and physics
parameters. Operations: multiply, add, replace, sign flip. NaN/Inf results are
rejected (mutation skipped) unless explicitly allowed in settings.
"""

from __future__ import annotations

import math
from typing import Optional

from ..history import MutationRecord
from .base import Mutation, MutationContext

_FLOAT_MAX = 3.4028234663852886e38


class Float32Mutation(Mutation):
    name = "float32"

    #: operations chosen from, weighted equally by default
    OPS = ("multiply", "add", "sign_flip", "replace")

    def apply(self, ctx: MutationContext, index: int) -> Optional[MutationRecord]:
        off = ctx.pick_span(4)
        if off is None:
            return None
        region = ctx.lookup(off)
        endian = (region.endianness if region and region.endianness
                  else ctx.settings.endianness)

        old = ctx.read_f32(off, endian)
        # Skip garbage that is already non-finite unless allowed.
        if not math.isfinite(old) and not ctx.settings.allow_nan:
            return ctx.make_record(index, "float32", off, size=4, skipped=True,
                                   note="skipped: source non-finite")

        mag = ctx.settings.magnitude
        op = ctx.rng.choice(self.OPS)
        if op == "multiply":
            # Example spec: value *= random(0.5, 2.0); scaled by magnitude.
            lo = max(0.0, 1.0 - mag)
            hi = 1.0 + mag * 2.0
            factor = ctx.rng.uniform(lo, hi)
            new = old * factor
            note = f"x{factor:.3f}"
        elif op == "add":
            scale = (abs(old) + 1.0) * mag
            delta = ctx.rng.uniform(-scale, scale)
            new = old + delta
            note = f"+{delta:.3f}"
        elif op == "sign_flip":
            new = -old
            note = "sign"
        else:  # replace
            scale = (abs(old) + 1.0) * (1.0 + mag * 4.0)
            new = ctx.rng.uniform(-scale, scale)
            note = "replace"

        if not ctx.settings.allow_nan:
            if not math.isfinite(new) or abs(new) > _FLOAT_MAX:
                return ctx.make_record(index, f"float_{op}", off, size=4,
                                       skipped=True,
                                       note="skipped: would produce NaN/Inf")

        ctx.write_f32(off, new, endian)
        shown_new = ctx.read_f32(off, endian)
        return ctx.make_record(index, f"float_{op}", off, size=4,
                               before=f"{old:.6g}", after=f"{shown_new:.6g}",
                               note=note)
