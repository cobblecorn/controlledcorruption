"""Differential analysis: find the byte ranges that differ between two files.

Useful for turning a patched / modded / translated ROM into a set of regions,
or for confirming that a corruption only touched what it should have.
"""

from __future__ import annotations

from typing import List, Tuple

from .regions import Interval, Region


def changed_intervals(a: bytes, b: bytes, *, merge_gap: int = 16) -> List[Interval]:
    """Return ``(start, end)`` ranges where ``a`` and ``b`` differ.

    Runs within ``merge_gap`` bytes of each other are coalesced so the result
    is a handful of meaningful regions rather than thousands of single bytes.
    Trailing bytes of the longer file are reported as one changed range.
    """
    n = min(len(a), len(b))
    runs: List[Interval] = []
    start = None
    for i in range(n):
        if a[i] != b[i]:
            if start is None:
                start = i
        else:
            if start is not None:
                runs.append((start, i))
                start = None
    if start is not None:
        runs.append((start, n))
    if len(a) != len(b):
        runs.append((n, max(len(a), len(b))))

    if not runs:
        return []
    merged: List[Interval] = [runs[0]]
    for s, e in runs[1:]:
        ls, le = merged[-1]
        if s - le <= merge_gap:
            merged[-1] = (ls, e)
        else:
            merged.append((s, e))
    return merged


def diff_regions(a: bytes, b: bytes, *, merge_gap: int = 16,
                 category: str = "unknown") -> List[Region]:
    """Same as :func:`changed_intervals` but as named :class:`Region` objects."""
    out = []
    for idx, (s, e) in enumerate(changed_intervals(a, b, merge_gap=merge_gap)):
        out.append(Region(
            name=f"diff_{idx:03d}",
            start=s, end=e, category=category, confidence=0.5,
            source="diff", description="range that differs between the two files",
        ))
    return out


def diff_summary(a: bytes, b: bytes, *, merge_gap: int = 16) -> dict:
    intervals = changed_intervals(a, b, merge_gap=merge_gap)
    total = sum(e - s for s, e in intervals)
    return {
        "size_a": len(a),
        "size_b": len(b),
        "changed_ranges": len(intervals),
        "changed_bytes": total,
        "intervals": intervals,
    }
