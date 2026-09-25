"""Emulator abstraction.

The core corruption engine is deliberately decoupled from any emulator. An
adapter only needs to launch a ROM, report whether it is running, and detect an
unexpected exit (a crash signal for guided-fuzzing style workflows later).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class LaunchStatus:
    running: bool
    returncode: Optional[int] = None
    crashed: bool = False
    detail: str = ""


class EmulatorAdapter:
    id: str = "base"
    name: str = "Base Emulator"

    def launch(self, rom_path: str) -> None:  # pragma: no cover - side effects
        raise NotImplementedError

    def terminate(self) -> None:  # pragma: no cover
        raise NotImplementedError

    def is_running(self) -> bool:  # pragma: no cover
        raise NotImplementedError

    def status(self) -> LaunchStatus:  # pragma: no cover
        raise NotImplementedError
