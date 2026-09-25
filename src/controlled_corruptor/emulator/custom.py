"""Custom-command emulator adapter.

The most portable adapter: the user supplies a command template containing a
``{ROM}`` placeholder (and optionally ``{ROM_DIR}``, ``{ROM_NAME}``). This
covers RetroArch, Project64, Dolphin, PCSX2, DuckStation, RPCS3, Xenia, and
anything else launchable from a command line, without a dedicated class each.

Example template::

    "/usr/bin/retroarch" -L cores/mupen64plus_libretro.so "{ROM}"
    "C:\\Emulators\\Dolphin.exe" "{ROM}"
    "xenia.exe" "{ROM}"
"""

from __future__ import annotations

import os
import shlex
import subprocess
from typing import List, Optional

from .base import EmulatorAdapter, LaunchStatus


class CustomCommandEmulator(EmulatorAdapter):
    id = "custom"
    name = "Custom Command"

    def __init__(
        self,
        command: str,
        *,
        name: str = "Custom Command",
        working_dir: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        self.command = command
        self.name = name
        self.working_dir = working_dir
        self.timeout = timeout
        self._proc: Optional[subprocess.Popen] = None

    # -- command building ---------------------------------------------------
    def build_args(self, rom_path: str) -> List[str]:
        rom_path = os.path.abspath(rom_path)
        subs = {
            "ROM": rom_path,
            "ROM_DIR": os.path.dirname(rom_path),
            "ROM_NAME": os.path.basename(rom_path),
        }
        # Tokenize first, then substitute per-token so paths with spaces inside
        # a quoted "{ROM}" survive intact.
        tokens = shlex.split(self.command, posix=(os.name != "nt"))
        if not tokens:
            raise ValueError("empty emulator command")
        out: List[str] = []
        for tok in tokens:
            for key, val in subs.items():
                tok = tok.replace("{" + key + "}", val)
            out.append(tok)
        # If the template never referenced {ROM}, append the ROM as last arg.
        if "{ROM}" not in self.command:
            out.append(rom_path)
        return out

    # -- lifecycle ----------------------------------------------------------
    def launch(self, rom_path: str) -> None:
        args = self.build_args(rom_path)
        self._proc = subprocess.Popen(args, cwd=self.working_dir)

    def terminate(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def wait(self, timeout: Optional[float] = None) -> LaunchStatus:
        if self._proc is None:
            return LaunchStatus(running=False, detail="not launched")
        try:
            rc = self._proc.wait(timeout=timeout if timeout is not None else self.timeout)
        except subprocess.TimeoutExpired:
            return LaunchStatus(running=True, detail="still running (timeout)")
        return LaunchStatus(running=False, returncode=rc, crashed=(rc not in (0, None)),
                            detail=f"exited with code {rc}")

    def status(self) -> LaunchStatus:
        if self._proc is None:
            return LaunchStatus(running=False, detail="not launched")
        rc = self._proc.poll()
        if rc is None:
            return LaunchStatus(running=True, detail="running")
        return LaunchStatus(running=False, returncode=rc, crashed=(rc not in (0, None)),
                            detail=f"exited with code {rc}")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "command": self.command,
            "working_dir": self.working_dir,
            "timeout": self.timeout,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CustomCommandEmulator":
        return cls(
            command=d["command"],
            name=d.get("name", "Custom Command"),
            working_dir=d.get("working_dir"),
            timeout=d.get("timeout"),
        )
