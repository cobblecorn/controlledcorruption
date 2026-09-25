"""Mutation strategy base class and the shared mutation context.

Each mutation is a small strategy object. It receives a
:class:`MutationContext` (the working buffer, the PRNG, the settings and a way
to pick a legal offset) and either performs one change and returns a
:class:`MutationRecord`, or returns ``None`` when it could not act (e.g. no
room), which the engine logs as a skip.

Strategies must consume the PRNG in a fixed order so output stays
deterministic for a given seed.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Callable, Optional

from ..history import MutationRecord
from ..prng import Rng
from ..regions import Region
from ..settings import MutationSettings

# A function that returns a legal start offset for a span of the given size,
# guaranteed to lie fully inside the effective mutable area, or None.
SpanPicker = Callable[[int], Optional[int]]


@dataclass
class MutationContext:
    out: bytearray
    rng: Rng
    settings: MutationSettings
    pick_span: SpanPicker
    lookup: Callable[[int], Optional[Region]]

    # -- numeric helpers ----------------------------------------------------
    def endian_char(self, region: Optional[Region]) -> str:
        endian = region.endianness if region and region.endianness else self.settings.endianness
        return "<" if endian == "little" else ">"

    def read_int(self, offset: int, size: int, endian: str, signed: bool) -> int:
        return int.from_bytes(self.out[offset:offset + size], endian, signed=signed)

    def write_int(self, offset: int, size: int, value: int, endian: str) -> None:
        mask = (1 << (size * 8)) - 1
        self.out[offset:offset + size] = (value & mask).to_bytes(size, endian)

    def read_f32(self, offset: int, endian: str) -> float:
        fmt = ("<" if endian == "little" else ">") + "f"
        return struct.unpack_from(fmt, self.out, offset)[0]

    def write_f32(self, offset: int, value: float, endian: str) -> None:
        fmt = ("<" if endian == "little" else ">") + "f"
        struct.pack_into(fmt, self.out, offset, value)

    def make_record(self, index: int, operation: str, offset: int, **kw) -> MutationRecord:
        region = self.lookup(offset)
        return MutationRecord(
            index=index,
            operation=operation,
            offset=offset,
            region=region.name if region else None,
            category=region.category if region else None,
            **kw,
        )


class Mutation:
    """Base strategy. Subclasses set ``name`` and implement :meth:`apply`."""

    name: str = "base"

    def apply(self, ctx: MutationContext, index: int) -> Optional[MutationRecord]:
        raise NotImplementedError
