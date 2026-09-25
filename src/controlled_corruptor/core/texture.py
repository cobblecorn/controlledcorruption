"""Semantic texture corruption.

Interprets a region as pixels (or palette entries) in a known format and applies
image-aware operations -- channel shift/swap/scale, invert, and palette
rotate/shuffle -- instead of arbitrary byte noise. This produces the classic
"corrupted texture" looks (colour swaps, palette scrambles) reproducibly.

Supported pixel formats:
    rgba8888, rgb888          -- 8-bit byte channels
    rgba5551, rgb565          -- 16-bit packed channels (endian-aware)

Palette operations (rotate/shuffle) are format-agnostic: they rearrange
fixed-size entries.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from .history import MutationLog, MutationRecord
from .prng import Rng

CHANNEL_OPS = ("channel_shift", "channel_swap", "channel_scale", "invert")
PALETTE_OPS = ("palette_rotate", "palette_shuffle")
OPS = CHANNEL_OPS + PALETTE_OPS


@dataclass
class PixelFormat:
    name: str
    bpp: int                 # bytes per pixel
    channel_bits: Tuple[int, ...]  # bits per channel (order = decode order)
    packed: bool             # True: bitfields in a bpp-byte word; False: byte channels
    endian: str = "big"

    @property
    def maxvals(self) -> Tuple[int, ...]:
        return tuple((1 << b) - 1 for b in self.channel_bits)

    def decode(self, data: bytes, off: int) -> List[int]:
        if not self.packed:
            return [data[off + i] for i in range(len(self.channel_bits))]
        word = int.from_bytes(data[off:off + self.bpp],
                              "little" if self.endian == "little" else "big")
        vals: List[int] = []
        shift = sum(self.channel_bits)
        for bits in self.channel_bits:
            shift -= bits
            vals.append((word >> shift) & ((1 << bits) - 1))
        return vals

    def encode(self, data: bytearray, off: int, vals: Sequence[int]) -> None:
        if not self.packed:
            for i, v in enumerate(vals):
                data[off + i] = v & 0xFF
            return
        word = 0
        shift = sum(self.channel_bits)
        for bits, v in zip(self.channel_bits, vals):
            shift -= bits
            word |= (v & ((1 << bits) - 1)) << shift
        data[off:off + self.bpp] = word.to_bytes(
            self.bpp, "little" if self.endian == "little" else "big")


FORMATS = {
    "rgba8888": lambda endian="big": PixelFormat("rgba8888", 4, (8, 8, 8, 8), False, endian),
    "rgb888": lambda endian="big": PixelFormat("rgb888", 3, (8, 8, 8), False, endian),
    "rgba5551": lambda endian="big": PixelFormat("rgba5551", 2, (5, 5, 5, 1), True, endian),
    "rgb565": lambda endian="big": PixelFormat("rgb565", 2, (5, 6, 5), True, endian),
}


def get_format(name: str, endian: str = "big") -> PixelFormat:
    try:
        return FORMATS[name](endian)
    except KeyError:
        raise ValueError(f"unknown pixel format {name!r}; choose from {', '.join(FORMATS)}")


@dataclass
class TextureSettings:
    op: str = "channel_swap"
    strength: float = 0.5            # for shift/scale
    channel_a: int = 0               # for swap
    channel_b: int = 2
    channel: int = -1                # target channel for invert (-1 = all)
    rotate_by: int = 1               # for palette_rotate
    entry_size: int = 0              # palette entry bytes (0 => use format bpp)
    seed: object = 0


def corrupt_texture(
    out: bytearray,
    start: int,
    end: int,
    fmt: Optional[PixelFormat],
    settings: TextureSettings,
    *,
    region_name: Optional[str] = None,
    log: Optional[MutationLog] = None,
) -> MutationLog:
    """Apply a texture operation to ``out[start:end]``. Mutates in place."""
    log = log or MutationLog()
    op = settings.op
    if op not in OPS:
        raise ValueError(f"unknown texture op {op!r}; choose from {', '.join(OPS)}")

    if op in PALETTE_OPS:
        return _palette_op(out, start, end, settings, region_name, log)

    if fmt is None:
        raise ValueError("channel operations require a pixel format")
    rng = Rng(settings.seed)
    bpp = fmt.bpp
    maxvals = fmt.maxvals
    nch = len(fmt.channel_bits)
    idx = 0
    for off in range(start, end - bpp + 1, bpp):
        vals = fmt.decode(out, off)
        before = list(vals)
        if op == "channel_swap":
            a, b = settings.channel_a, settings.channel_b
            if a < nch and b < nch:
                vals[a], vals[b] = vals[b], vals[a]
        elif op == "channel_shift":
            for c in range(nch):
                if settings.channel not in (-1, c):
                    continue
                reach = max(1, round(settings.strength * maxvals[c]))
                vals[c] = max(0, min(maxvals[c], vals[c] + rng.randint(-reach, reach)))
        elif op == "channel_scale":
            for c in range(nch):
                if settings.channel not in (-1, c):
                    continue
                vals[c] = max(0, min(maxvals[c], round(vals[c] * (1.0 + settings.strength))))
        elif op == "invert":
            for c in range(nch):
                if settings.channel not in (-1, c):
                    continue
                vals[c] = maxvals[c] - vals[c]
        if vals != before:
            fmt.encode(out, off, vals)
            idx += 1
    log.add(MutationRecord(index=0, operation=f"texture_{op}", offset=start,
                           size=end - start, region=region_name,
                           note=f"{fmt.name}, {idx} pixels changed"))
    return log


def _palette_op(out: bytearray, start: int, end: int, settings: TextureSettings,
                region_name: Optional[str], log: MutationLog) -> MutationLog:
    entry = settings.entry_size or 2
    n = (end - start) // entry
    if n < 2:
        log.add(MutationRecord(index=0, operation=f"texture_{settings.op}",
                               offset=start, size=end - start, skipped=True,
                               region=region_name, note="too few palette entries"))
        return log
    entries = [bytes(out[start + i * entry:start + (i + 1) * entry]) for i in range(n)]
    if settings.op == "palette_rotate":
        k = settings.rotate_by % n
        entries = entries[k:] + entries[:k]
        note = f"rotate {k} of {n} entries"
    else:  # palette_shuffle -- deterministic Fisher-Yates
        rng = Rng(settings.seed)
        for i in range(n - 1, 0, -1):
            j = rng.randbelow(i + 1)
            entries[i], entries[j] = entries[j], entries[i]
        note = f"shuffle {n} entries"
    for i, e in enumerate(entries):
        out[start + i * entry:start + (i + 1) * entry] = e
    log.add(MutationRecord(index=0, operation=f"texture_{settings.op}", offset=start,
                           size=end - start, region=region_name, note=note))
    return log
