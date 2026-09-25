"""Interactive mutation evolution.

Implements the handoff's "mutation evolution" idea on top of the non-destructive
layer stack: propose a candidate (original + kept layers + one new layer); if
the user keeps it, the new layer joins the stack and the next proposal builds on
top; if rejected, it is discarded and a fresh proposal is made.

Because output is always rebuilt from the *original* plus the kept layers, there
is no cumulative accidental corruption -- rejecting always returns to the last
kept state exactly.

The class is UI/emulator-agnostic: a front-end calls :meth:`propose`, shows the
result (e.g. launches an emulator), then calls :meth:`keep` or :meth:`reject`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from ..platforms.base import PlatformAdapter
from ..profiles import GameProfile
from .binary import BinaryFile
from .engine import Engine
from .history import MutationLog
from .pipeline import gather_regions
from .project import CorruptionProject, Layer
from .regions import Interval
from .settings import MutationSettings


@dataclass
class Candidate:
    generation: int
    layer: Layer
    output: bytes
    log: MutationLog


@dataclass
class Evolver:
    """Drives generational, keep/reject corruption evolution."""

    binary: BinaryFile
    platform: PlatformAdapter
    profile: Optional[GameProfile] = None
    categories: Optional[Sequence[str]] = None
    target_intervals: Optional[Sequence[Interval]] = None
    repair_checksum: bool = True
    base_settings: MutationSettings = field(default_factory=MutationSettings)

    kept: List[Layer] = field(default_factory=list)
    generation: int = 0
    _pending: Optional[Candidate] = None

    # -- core ---------------------------------------------------------------
    def _render(self, layers: Sequence[Layer]) -> "tuple[bytes, MutationLog]":
        """Rebuild output from original + the given layers (non-destructive)."""
        working = self.binary.data
        combined = MutationLog()
        for layer in layers:
            if not layer.enabled:
                continue
            targets, protected = gather_regions(
                self.binary, self.platform, self.profile,
                extra_protected=layer.extra_protected)
            res = Engine(layer.settings).run(
                working, targets=targets, protected=protected,
                target_intervals=layer.target_intervals, categories=layer.categories)
            working = res.data
            combined.records.extend(res.log.records)
        if self.repair_checksum:
            working = self.platform.repair_checksum(working)
        return working, combined

    def current_output(self) -> bytes:
        """The output of the currently-kept stack (original if empty)."""
        out, _ = self._render(self.kept)
        return out

    def propose(self, seed: object, *, intensity: Optional[float] = None,
                categories: Optional[Sequence[str]] = None) -> Candidate:
        """Generate the next candidate layered on top of the kept stack."""
        self.generation += 1
        if intensity is not None:
            settings = MutationSettings.from_intensity(
                intensity, seed=seed, types=list(self.base_settings.types))
        else:
            settings = MutationSettings.from_dict(
                {**self.base_settings.to_dict(), "seed": seed})
        layer = Layer(
            name=f"Gen {self.generation}",
            settings=settings,
            categories=list(categories) if categories is not None
            else (list(self.categories) if self.categories else None),
            target_intervals=list(self.target_intervals) if self.target_intervals else None,
        )
        output, log = self._render(self.kept + [layer])
        self._pending = Candidate(self.generation, layer, output, log)
        return self._pending

    def keep(self) -> None:
        """Accept the pending candidate: its layer joins the kept stack."""
        if self._pending is None:
            raise RuntimeError("no pending candidate to keep; call propose() first")
        self.kept.append(self._pending.layer)
        self._pending = None

    def reject(self) -> None:
        """Discard the pending candidate; the kept stack is unchanged."""
        self._pending = None

    def undo(self) -> Optional[Layer]:
        """Remove the most recently kept layer."""
        return self.kept.pop() if self.kept else None

    # -- export -------------------------------------------------------------
    def to_project(self, *, notes: str = "") -> CorruptionProject:
        """Serialize the kept evolution as a reproducible project."""
        return CorruptionProject(
            source_sha256=self.binary.sha256,
            source_filename=self.binary.filename,
            source_size=self.binary.size,
            platform=self.platform.id,
            profile_id=(self.profile.id if self.profile else None),
            repair_checksum=self.repair_checksum,
            layers=list(self.kept),
            notes=notes or f"Evolved corruption ({len(self.kept)} kept generations)",
        )
