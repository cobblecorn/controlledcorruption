"""Region model and interval arithmetic.

A :class:`Region` describes *where* in a binary something lives and *what*
kind of data it is -- but never *how* it will be mutated (that is the job of
mutation strategies). Offsets are byte positions; ``end`` is exclusive.

The interval helpers compute the effective mutable area:

    mutable target regions  MINUS  protected regions  =  effective intervals

Protected regions always win, matching the handoff requirement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence, Tuple

Interval = Tuple[int, int]  # (start, end) with end exclusive


# --------------------------------------------------------------------------
# Standard corruption categories (profiles may add their own tags freely).
# --------------------------------------------------------------------------
CATEGORIES = (
    "models",
    "animations",
    "textures",
    "maps",
    "collision",
    "entities",
    "scripts",
    "audio",
    "text",
    "physics",
    "gameplay",
    "executable",
    "filesystem",
    "header",
    "unknown",
)


def parse_offset(value: object) -> int:
    """Parse an int or a hex/decimal string like ``"0x01738000"``."""
    if isinstance(value, bool):
        raise TypeError("offset cannot be a bool")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        s = value.strip().replace("_", "")
        if s.lower().startswith("0x"):
            return int(s, 16)
        return int(s, 10)
    raise TypeError(f"cannot parse offset from {value!r}")


@dataclass
class Region:
    """A named span of a binary file.

    ``mutable`` distinguishes *target* regions (may be corrupted) from
    *protected* regions (must never change). Protection is enforced by the
    engine regardless of this flag when the region is supplied as protected.
    """

    name: str
    start: int
    end: int  # exclusive
    category: str = "unknown"
    mutable: bool = True
    confidence: float = 1.0
    endianness: str = "little"  # "little" or "big"
    data_type: Optional[str] = None  # e.g. "float32", "int16", "raw"
    alignment: int = 1
    tags: List[str] = field(default_factory=list)
    description: str = ""
    source: str = ""  # where this region knowledge came from (profile id, user, heuristic)

    def __post_init__(self) -> None:
        self.start = parse_offset(self.start)
        self.end = parse_offset(self.end)
        if self.end < self.start:
            raise ValueError(
                f"region {self.name!r}: end 0x{self.end:X} < start 0x{self.start:X}"
            )

    @property
    def size(self) -> int:
        return self.end - self.start

    @property
    def interval(self) -> Interval:
        return (self.start, self.end)

    def matches(self, categories: Optional[Sequence[str]]) -> bool:
        """True if this region belongs to any of ``categories`` (by category or tag)."""
        if not categories:
            return True
        wanted = {c.lower() for c in categories}
        if self.category.lower() in wanted:
            return True
        return any(t.lower() in wanted for t in self.tags)

    # -- (de)serialization --------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "start": f"0x{self.start:08X}",
            "end": f"0x{self.end:08X}",
            "category": self.category,
            "mutable": self.mutable,
            "confidence": self.confidence,
            "endianness": self.endianness,
            "data_type": self.data_type,
            "alignment": self.alignment,
            "tags": list(self.tags),
            "description": self.description,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Region":
        return cls(
            name=d["name"],
            start=parse_offset(d["start"]),
            end=parse_offset(d["end"]),
            category=d.get("category", "unknown"),
            mutable=d.get("mutable", True),
            confidence=d.get("confidence", 1.0),
            endianness=d.get("endianness", "little"),
            data_type=d.get("data_type"),
            alignment=d.get("alignment", 1),
            tags=list(d.get("tags", [])),
            description=d.get("description", ""),
            source=d.get("source", ""),
        )


# --------------------------------------------------------------------------
# Interval arithmetic
# --------------------------------------------------------------------------
def clamp_intervals(intervals: Iterable[Interval], size: int) -> List[Interval]:
    """Clip intervals to ``[0, size)`` and drop empties."""
    out: List[Interval] = []
    for s, e in intervals:
        s = max(0, s)
        e = min(size, e)
        if e > s:
            out.append((s, e))
    return out


def merge_intervals(intervals: Iterable[Interval]) -> List[Interval]:
    """Sort and coalesce overlapping/adjacent intervals."""
    items = sorted((s, e) for s, e in intervals if e > s)
    if not items:
        return []
    merged: List[Interval] = [items[0]]
    for s, e in items[1:]:
        ls, le = merged[-1]
        if s <= le:  # overlap or touch
            merged[-1] = (ls, max(le, e))
        else:
            merged.append((s, e))
    return merged


def subtract_intervals(
    base: Iterable[Interval], holes: Iterable[Interval]
) -> List[Interval]:
    """Return ``base`` minus ``holes`` as a list of disjoint intervals."""
    base_m = merge_intervals(base)
    holes_m = merge_intervals(holes)
    if not holes_m:
        return base_m

    result: List[Interval] = []
    for s, e in base_m:
        cur = s
        for hs, he in holes_m:
            if he <= cur or hs >= e:
                continue  # hole outside this segment
            if hs > cur:
                result.append((cur, min(hs, e)))
            cur = max(cur, he)
            if cur >= e:
                break
        if cur < e:
            result.append((cur, e))
    return [iv for iv in result if iv[1] > iv[0]]


def total_length(intervals: Iterable[Interval]) -> int:
    return sum(e - s for s, e in intervals)


def region_lookup(regions: Sequence[Region]):
    """Return a function mapping an offset to the first containing region name.

    Used only for enriching mutation log entries; ``None`` when unknown.
    """
    ordered = sorted(regions, key=lambda r: (r.start, r.end))

    def lookup(offset: int) -> Optional[Region]:
        for r in ordered:
            if r.start <= offset < r.end:
                return r
            if r.start > offset:
                break
        return None

    return lookup
