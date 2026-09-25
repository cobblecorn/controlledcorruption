"""Guided-fuzz region sweep and crash/survival heat map.

Mutate one block of the ROM at a time, run each result through a **tester**, and
record whether it survived or crashed. Over a full sweep this builds a heat map
that hints at which regions are critical (code/tables) versus safe (assets).

The tester is a plain callable ``(bytes) -> Outcome`` so the engine stays
emulator-agnostic. :func:`emulator_tester` wraps a real emulator (launch, wait,
inspect exit) for interactive use; tests inject a deterministic fake tester.

This is experimental/stretch functionality -- the MVP does not depend on it.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence

from .binary import BinaryFile
from .engine import Engine
from .regions import Interval, merge_intervals, subtract_intervals
from .settings import MutationSettings

#: Outcome labels a tester may return.
BOOT = "boot"       # ran/booted successfully
CRASH = "crash"     # crashed or exited abnormally
HANG = "hang"       # never exited within the timeout (often = still running/ok)
ERROR = "error"     # could not test

Tester = Callable[[bytes], str]


@dataclass
class BlockOutcome:
    start: int
    end: int
    attempts: int = 0
    boot: int = 0
    crash: int = 0
    hang: int = 0
    error: int = 0

    def record(self, outcome: str) -> None:
        self.attempts += 1
        setattr(self, outcome, getattr(self, outcome, 0) + 1)

    @property
    def safety(self) -> float:
        """Fraction of attempts that did not crash (higher = safer to corrupt)."""
        if self.attempts == 0:
            return 0.0
        return (self.attempts - self.crash) / self.attempts

    def to_dict(self) -> dict:
        return {
            "start": f"0x{self.start:08X}", "end": f"0x{self.end:08X}",
            "attempts": self.attempts, "boot": self.boot, "crash": self.crash,
            "hang": self.hang, "error": self.error,
            "safety": round(self.safety, 4),
        }


@dataclass
class HeatMap:
    blocks: List[BlockOutcome] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"blocks": [b.to_dict() for b in self.blocks]}

    def render(self, width: int = 60) -> str:
        bars = " .:-=+*#%@"
        lines = []
        for b in self.blocks:
            idx = min(len(bars) - 1, int(b.safety * (len(bars) - 1)))
            lines.append(f"0x{b.start:08X} {bars[idx]} safety={b.safety:.2f} "
                         f"(boot={b.boot} crash={b.crash} hang={b.hang})")
        return "\n".join(lines)

    def critical_blocks(self, threshold: float = 0.5) -> List[BlockOutcome]:
        return [b for b in self.blocks if b.attempts and b.safety < threshold]


def _mutable_blocks(size: int, block_size: int,
                    mutable: Sequence[Interval]) -> List[Interval]:
    blocks: List[Interval] = []
    for s, e in mutable:
        pos = s
        while pos < e:
            blocks.append((pos, min(pos + block_size, e)))
            pos += block_size
    return blocks


def sweep(
    binary: BinaryFile,
    tester: Tester,
    *,
    block_size: int = 0x1000,
    settings: Optional[MutationSettings] = None,
    protected_intervals: Optional[Sequence[Interval]] = None,
    target_intervals: Optional[Sequence[Interval]] = None,
    platform=None,
    repair_checksum: bool = True,
    trials: int = 1,
    seed_prefix: str = "sweep",
    on_progress: Optional[Callable[[int, int, BlockOutcome], None]] = None,
) -> HeatMap:
    """Mutate each block in turn and classify the result with ``tester``.

    Returns a :class:`HeatMap`. ``platform`` (or auto-detected) supplies
    protected regions and checksum repair; those protected bytes are never
    mutated and their blocks are skipped.
    """
    from .. import platforms as platforms_mod

    plat = platform or platforms_mod.detect(binary.data)
    size = binary.size

    base_targets: List[Interval] = list(target_intervals or [(0, size)])
    protected: List[Interval] = list(protected_intervals or [])
    protected += [r.interval for r in plat.protected_regions(binary.data)]
    mutable = merge_intervals(subtract_intervals(base_targets, protected))

    blocks = _mutable_blocks(size, block_size, mutable)
    heat = HeatMap()

    for bi, (bs, be) in enumerate(blocks):
        outcome = BlockOutcome(start=bs, end=be)
        for t in range(max(1, trials)):
            s = settings or MutationSettings(density=0.05, magnitude=0.6)
            s = MutationSettings.from_dict({**s.to_dict(),
                                            "seed": f"{seed_prefix}-{bs:08x}-{t}"})
            result = Engine(s).run(binary.data, target_intervals=[(bs, be)])
            out = result.data
            if repair_checksum:
                out = plat.repair_checksum(out)
            try:
                label = tester(out)
            except Exception:
                label = ERROR
            if label not in (BOOT, CRASH, HANG, ERROR):
                label = ERROR
            outcome.record(label)
        heat.blocks.append(outcome)
        if on_progress:
            on_progress(bi + 1, len(blocks), outcome)
    return heat


def emulator_tester(command: str, *, boot_time: float = 6.0,
                    timeout: float = 20.0) -> Tester:
    """Build a tester that launches a real emulator via a ``{ROM}`` command.

    Heuristic: if the emulator is still running after ``boot_time`` it is
    treated as a successful boot (then terminated); if it exits early with a
    non-zero code it is a crash; a clean early exit is a boot.
    """
    from ..emulator import CustomCommandEmulator

    def test(data: bytes) -> str:
        fd, path = tempfile.mkstemp(suffix=".rom")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            emu = CustomCommandEmulator(command, timeout=timeout)
            emu.launch(path)
            status = emu.wait(timeout=boot_time)
            if status.running:
                emu.terminate()
                return HANG  # survived past boot_time == booted OK
            if status.crashed:
                return CRASH
            return BOOT
        except Exception:
            return ERROR
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    return test
