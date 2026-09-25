"""Binary search and structure-heuristic utilities.

These make the tool useful even when no profile exists: search for bytes /
ASCII / integers / floats, list strings, measure entropy, and take *low
confidence* guesses at structure (pointer candidates, vertex-like float
triplets). Anything guessed is explicitly marked experimental by the caller.
"""

from __future__ import annotations

import math
import re
import struct
from dataclasses import dataclass
from typing import List, Optional, Tuple


# --------------------------------------------------------------------------
# exact searches
# --------------------------------------------------------------------------
def search_bytes(data: bytes, pattern: bytes, *, limit: Optional[int] = None) -> List[int]:
    """All offsets where ``pattern`` occurs (overlapping)."""
    if not pattern:
        return []
    out: List[int] = []
    start = 0
    while True:
        idx = data.find(pattern, start)
        if idx == -1:
            break
        out.append(idx)
        start = idx + 1
        if limit is not None and len(out) >= limit:
            break
    return out


def search_int(data: bytes, value: int, *, size: int = 4, endian: str = "little",
               signed: bool = False, limit: Optional[int] = None) -> List[int]:
    e = "<" if endian == "little" else ">"
    codes = {1: "b", 2: "h", 4: "i", 8: "q"} if signed else {1: "B", 2: "H", 4: "I", 8: "Q"}
    if size not in codes:
        raise ValueError("size must be 1, 2, 4 or 8")
    pattern = struct.pack(e + codes[size], value)
    return search_bytes(data, pattern, limit=limit)


def search_float(data: bytes, value: float, *, tol: float = 1e-3, endian: str = "little",
                 double: bool = False, limit: Optional[int] = None) -> List[int]:
    """Offsets whose float32/float64 value is within ``tol`` of ``value``."""
    e = "<" if endian == "little" else ">"
    fmt = e + ("d" if double else "f")
    size = 8 if double else 4
    out: List[int] = []
    for off in range(0, len(data) - size + 1):
        v = struct.unpack_from(fmt, data, off)[0]
        if math.isfinite(v) and abs(v - value) <= tol:
            out.append(off)
            if limit is not None and len(out) >= limit:
                break
    return out


# --------------------------------------------------------------------------
# strings
# --------------------------------------------------------------------------
@dataclass
class FoundString:
    offset: int
    text: str


def find_strings(data: bytes, *, min_len: int = 4,
                 limit: Optional[int] = None) -> List[FoundString]:
    """Printable-ASCII runs of at least ``min_len`` characters."""
    out: List[FoundString] = []
    for m in re.finditer(rb"[\x20-\x7e]{%d,}" % max(1, min_len), data):
        out.append(FoundString(m.start(), m.group().decode("ascii", "replace")))
        if limit is not None and len(out) >= limit:
            break
    return out


# --------------------------------------------------------------------------
# entropy
# --------------------------------------------------------------------------
def entropy_blocks(data: bytes, *, blocks: int = 64) -> List[Tuple[int, float]]:
    """Shannon entropy (0..8 bits) for ``blocks`` equal slices of the file.

    Returns ``(offset, entropy)`` pairs. High entropy suggests compressed /
    encrypted / audio data; low entropy suggests code, tables or padding.
    """
    if not data or blocks <= 0:
        return []
    size = max(1, len(data) // blocks)
    out: List[Tuple[int, float]] = []
    for off in range(0, len(data), size):
        chunk = data[off:off + size]
        if not chunk:
            continue
        counts = [0] * 256
        for b in chunk:
            counts[b] += 1
        n = len(chunk)
        ent = 0.0
        for c in counts:
            if c:
                p = c / n
                ent -= p * math.log2(p)
        out.append((off, ent))
    return out


def entropy_sparkline(pairs: List[Tuple[int, float]]) -> str:
    """Render entropy values (0..8) as a unicode block sparkline."""
    bars = " .:-=+*#%@"
    line = []
    for _off, ent in pairs:
        idx = min(len(bars) - 1, int(ent / 8.0 * (len(bars) - 1)))
        line.append(bars[idx])
    return "".join(line)


# --------------------------------------------------------------------------
# structure heuristics (LOW CONFIDENCE / EXPERIMENTAL)
# --------------------------------------------------------------------------
def pointer_candidates(data: bytes, *, size: int = 4, endian: str = "little",
                       base: int = 0, span: Optional[int] = None,
                       align: int = 4, limit: int = 1000) -> List[Tuple[int, int]]:
    """Offsets whose word value looks like a pointer into ``[base, base+span)``.

    Returns ``(offset, value)``. Purely heuristic.
    """
    e = "<" if endian == "little" else ">"
    fmt = e + {2: "H", 4: "I", 8: "Q"}[size]
    span = span if span is not None else len(data)
    lo, hi = base, base + span
    out: List[Tuple[int, int]] = []
    for off in range(0, len(data) - size + 1, align):
        v = struct.unpack_from(fmt, data, off)[0]
        if lo <= v < hi and v != 0:
            out.append((off, v))
            if len(out) >= limit:
                break
    return out


def float_triplets(data: bytes, *, endian: str = "little", stride: int = 12,
                   lo: float = -1e4, hi: float = 1e4, min_run: int = 4,
                   limit: int = 500) -> List[Tuple[int, int]]:
    """Find runs of vertex-like float32 triplets (x, y, z in a plausible range).

    Returns ``(start_offset, count)`` for each run of at least ``min_run``
    consecutive plausible triplets. Heuristic only.
    """
    e = "<" if endian == "little" else ">"
    n = len(data)

    def ok(off: int) -> bool:
        if off + 12 > n:
            return False
        for k in range(3):
            v = struct.unpack_from(e + "f", data, off + k * 4)[0]
            if not math.isfinite(v) or not (lo <= v <= hi):
                return False
        return True

    out: List[Tuple[int, int]] = []
    off = 0
    while off + 12 <= n:
        if ok(off):
            run = 0
            cur = off
            while cur + 12 <= n and ok(cur):
                run += 1
                cur += stride
            if run >= min_run:
                out.append((off, run))
                if len(out) >= limit:
                    break
            off = cur
        else:
            off += 4
    return out
