"""Semantic (Level-3) corruption of structured float data.

Where the generic engine flips arbitrary bytes, this module interprets a region
as an array of fixed-stride elements (e.g. float32 vertex triplets) and applies
a *coherent* transform to chosen components. This is what enables operations
like "scale the model on Y" or "mirror the X axis" or "amplify animation
values" instead of random noise.

Topology is preserved by construction: only the selected component floats inside
each element are touched; index / connectivity / other bytes in the stride are
left exactly as they were.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from .history import MutationLog, MutationRecord
from .prng import Rng

_FLOAT_MAX = 3.4028234663852886e38

#: Supported semantic operations.
OPS = ("scale", "stretch", "displace", "mirror", "flatten", "reverse")


@dataclass
class VertexLayout:
    """Describes an array of fixed-size elements with float32 components.

    ``component_offsets`` are byte offsets of each mutable float within one
    element (e.g. ``(0, 4, 8)`` for X, Y, Z at the start of a 32-byte vertex).
    """

    stride: int
    component_offsets: Sequence[int] = (0, 4, 8)
    endian: str = "little"

    @property
    def struct_prefix(self) -> str:
        return "<" if self.endian == "little" else ">"


@dataclass
class SemanticSettings:
    op: str = "scale"
    #: per-component strength (e.g. per-axis distortion). Missing => 0 (no change).
    strengths: Sequence[float] = field(default_factory=lambda: [0.4, 0.4, 0.4])
    avoid_nan: bool = True
    seed: object = 0


def _safe(new: float, old: float, avoid_nan: bool) -> float:
    if avoid_nan and (not math.isfinite(new) or abs(new) > _FLOAT_MAX):
        return old
    return new


def _transform(op: str, value: float, strength: float, rng: Rng) -> float:
    if strength == 0.0 and op not in ("reverse",):
        return value
    if op == "scale":
        return value * (1.0 + strength)
    if op == "stretch":
        return value * (1.0 + strength * 4.0)
    if op == "displace":
        span = (abs(value) + 1.0) * strength
        return value + rng.uniform(-span, span)
    if op == "mirror":
        return -value if strength > 0 else value
    if op == "flatten":
        keep = max(0.0, 1.0 - min(1.0, strength))
        return value * keep
    return value


def corrupt_region(
    out: bytearray,
    start: int,
    end: int,
    layout: VertexLayout,
    settings: SemanticSettings,
    *,
    region_name: Optional[str] = None,
    log: Optional[MutationLog] = None,
    base_index: int = 0,
) -> MutationLog:
    """Apply a semantic transform to the element array in ``out[start:end]``.

    Mutates ``out`` in place and returns a :class:`MutationLog`.
    """
    log = log or MutationLog()
    op = settings.op
    if op not in OPS:
        raise ValueError(f"unknown semantic op {op!r}; choose from {', '.join(OPS)}")
    fmt = layout.struct_prefix + "f"
    stride = layout.stride
    if stride <= 0:
        raise ValueError("stride must be positive")
    strengths = list(settings.strengths)
    rng = Rng(settings.seed)
    n_elems = max(0, (end - start) // stride)
    idx = base_index

    if op == "reverse":
        # Reverse the sequence of each selected component across all elements.
        for c, coff in enumerate(layout.component_offsets):
            strength = strengths[c] if c < len(strengths) else 0.0
            if strength <= 0:
                continue
            positions = [start + i * stride + coff for i in range(n_elems)
                         if start + i * stride + coff + 4 <= end]
            values = [struct.unpack_from(fmt, out, p)[0] for p in positions]
            for p, v in zip(positions, reversed(values)):
                struct.pack_into(fmt, out, p, v)
            log.add(MutationRecord(index=idx, operation="semantic_reverse",
                                   offset=positions[0] if positions else start,
                                   size=len(positions) * 4, region=region_name,
                                   note=f"component {c}, {len(positions)} values"))
            idx += 1
        return log

    for i in range(n_elems):
        base = start + i * stride
        for c, coff in enumerate(layout.component_offsets):
            off = base + coff
            if off + 4 > end:
                continue
            strength = strengths[c] if c < len(strengths) else 0.0
            old = struct.unpack_from(fmt, out, off)[0]
            if not math.isfinite(old) and settings.avoid_nan:
                continue
            new = _safe(_transform(op, old, strength, rng), old, settings.avoid_nan)
            if new != old:
                struct.pack_into(fmt, out, off, new)
                log.add(MutationRecord(
                    index=idx, operation=f"semantic_{op}", offset=off, size=4,
                    before=f"{old:.6g}", after=f"{new:.6g}", region=region_name,
                    note=f"component {c}"))
                idx += 1
    return log


def build_layout(stride: Optional[int] = None,
                 component_offsets: Optional[Sequence[int]] = None,
                 endian: str = "little") -> VertexLayout:
    """Convenience builder with vertex-triplet defaults."""
    comps = tuple(component_offsets) if component_offsets else (0, 4, 8)
    if stride is None:
        stride = (max(comps) + 4) if comps else 12
    return VertexLayout(stride=stride, component_offsets=comps, endian=endian)
