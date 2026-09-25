"""The mutation engine.

Pure and game-agnostic. Given input bytes, a set of target regions, a set of
protected regions, settings and a seed, it deterministically produces a new
byte string plus a mutation log.

Guarantees (all covered by tests):

* **Determinism** -- same input + regions + settings + seed => identical output.
* **Bounds**      -- no byte outside the effective mutable area ever changes.
* **Protection**  -- protected regions always win over target regions.
* **Immutability**-- the caller's input bytes are never modified in place.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

from . import mutations as mut
from .history import MutationLog
from .mutations.base import MutationContext
from .prng import PRNG_VERSION, Rng
from .regions import (
    Interval,
    Region,
    merge_intervals,
    region_lookup,
    subtract_intervals,
    total_length,
)
from .settings import MutationSettings


@dataclass
class EngineResult:
    data: bytes
    log: MutationLog
    mutable_bytes: int
    intervals: List[Interval]


class Engine:
    """Applies mutations to a copy of the input according to the settings."""

    def __init__(self, settings: MutationSettings):
        self.settings = settings
        if settings.prng_version != PRNG_VERSION:
            raise ValueError(
                f"project was made with PRNG {settings.prng_version!r} but this "
                f"build provides {PRNG_VERSION!r}; results would differ"
            )

    # -- public API ---------------------------------------------------------
    def run(
        self,
        data: bytes,
        *,
        targets: Optional[Sequence[Region]] = None,
        protected: Optional[Sequence[Region]] = None,
        target_intervals: Optional[Sequence[Interval]] = None,
        protected_intervals: Optional[Sequence[Interval]] = None,
        categories: Optional[Sequence[str]] = None,
    ) -> EngineResult:
        """Corrupt ``data`` and return the result.

        Regions may be supplied as :class:`Region` objects (which also enrich
        the log and provide endianness) and/or raw ``(start, end)`` intervals.
        ``categories`` filters the target regions by category/tag.
        """
        size = len(data)
        targets = list(targets or [])
        protected = list(protected or [])

        # Build target interval set.
        tgt: List[Interval] = list(target_intervals or [])
        for r in targets:
            if r.mutable and r.matches(categories):
                tgt.append(r.interval)
        if not tgt and not target_intervals:
            # Default target: the whole file (protection still applies).
            tgt = [(0, size)]

        # Build protected interval set.
        prot: List[Interval] = list(protected_intervals or [])
        for r in protected:
            prot.append(r.interval)

        effective = subtract_intervals(
            [(max(0, s), min(size, e)) for s, e in tgt],
            [(max(0, s), min(size, e)) for s, e in prot],
        )
        effective = merge_intervals(effective)
        mutable_bytes = total_length(effective)

        out = bytearray(data)  # private copy; caller's bytes untouched
        log = MutationLog()

        if mutable_bytes == 0:
            return EngineResult(data=bytes(out), log=log,
                                mutable_bytes=0, intervals=effective)

        rng = Rng(self.settings.seed)
        lookup = region_lookup(targets) if targets else (lambda _off: None)

        picker = _SpanPicker(effective, rng)
        ctx = MutationContext(
            out=out,
            rng=rng,
            settings=self.settings,
            pick_span=picker.pick,
            lookup=lookup,
        )

        num_ops = self._operation_count(mutable_bytes)
        types = [t for t in self.settings.types if t in mut.available()]
        if not types:
            types = ["byte_replace"]
        weights = [self.settings.weight_for(t) for t in types]

        for i in range(num_ops):
            name = rng.weighted_choice(types, weights)
            strategy = mut.get(name)
            record = strategy.apply(ctx, i)
            if record is None:
                # Strategy could not act (no room); log a generic skip.
                from .history import MutationRecord
                record = MutationRecord(index=i, operation=name, offset=0,
                                        skipped=True, note="skipped: no space")
            log.add(record)

        return EngineResult(data=bytes(out), log=log,
                            mutable_bytes=mutable_bytes, intervals=effective)

    # -- helpers ------------------------------------------------------------
    def _operation_count(self, mutable_bytes: int) -> int:
        n = round(self.settings.density * mutable_bytes)
        if self.settings.density > 0:
            n = max(1, n)
        return int(n)


class _SpanPicker:
    """Picks a uniformly-random start offset for a span of a given size.

    The span is guaranteed to fit entirely within a single effective interval,
    so it never crosses into protected/out-of-range bytes.
    """

    def __init__(self, intervals: Sequence[Interval], rng: Rng):
        self.intervals = list(intervals)
        self.rng = rng

    def pick(self, size: int) -> Optional[int]:
        if size <= 0:
            return None
        # Count legal start positions across all intervals.
        avail = [max(0, (e - s) - size + 1) for s, e in self.intervals]
        total = sum(avail)
        if total <= 0:
            return None
        r = self.rng.randbelow(total)
        for (s, _e), a in zip(self.intervals, avail):
            if a <= 0:
                continue
            if r < a:
                return s + r
            r -= a
        return None  # unreachable
