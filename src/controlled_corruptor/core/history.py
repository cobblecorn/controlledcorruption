"""Mutation records and the log/history container."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class MutationRecord:
    """A single applied (or skipped) mutation.

    ``index`` is the deterministic sequence number -- the same seed replays
    the same sequence, which is what makes a corruption reproducible.
    """

    index: int
    operation: str                 # e.g. "float_multiply", "byte_replace"
    offset: int                    # byte offset of the change
    size: int = 1                  # bytes affected
    before: Optional[str] = None   # human-readable prior value
    after: Optional[str] = None    # human-readable new value
    region: Optional[str] = None   # containing region name, if known
    category: Optional[str] = None
    note: str = ""                 # e.g. "skipped: protected", "clamped"
    skipped: bool = False

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "operation": self.operation,
            "offset": f"0x{self.offset:08X}",
            "size": self.size,
            "before": self.before,
            "after": self.after,
            "region": self.region,
            "category": self.category,
            "note": self.note,
            "skipped": self.skipped,
        }

    def describe(self) -> str:
        loc = f"0x{self.offset:08X}"
        where = f" [{self.region}]" if self.region else ""
        if self.skipped:
            return f"#{self.index} skipped {self.operation} @ {loc}{where} ({self.note})"
        change = ""
        if self.before is not None and self.after is not None:
            change = f" {self.before} -> {self.after}"
        return f"#{self.index} {self.operation} @ {loc}{where}{change}"


@dataclass
class MutationLog:
    """Ordered collection of mutation records plus summary counters."""

    records: List[MutationRecord] = field(default_factory=list)

    def add(self, record: MutationRecord) -> None:
        self.records.append(record)

    @property
    def applied(self) -> List[MutationRecord]:
        return [r for r in self.records if not r.skipped]

    @property
    def skipped(self) -> List[MutationRecord]:
        return [r for r in self.records if r.skipped]

    def summary(self) -> dict:
        ops: dict = {}
        for r in self.applied:
            ops[r.operation] = ops.get(r.operation, 0) + 1
        return {
            "total": len(self.records),
            "applied": len(self.applied),
            "skipped": len(self.skipped),
            "by_operation": ops,
        }

    def to_dict(self) -> dict:
        return {
            "summary": self.summary(),
            "records": [r.to_dict() for r in self.records],
        }
