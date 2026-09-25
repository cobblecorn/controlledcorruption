"""Emulator integration.

Presets are just named command templates for the custom adapter -- concrete
per-emulator classes can be added later, but the command template already
covers the common cases.
"""

from __future__ import annotations

from typing import Dict

from .base import EmulatorAdapter, LaunchStatus
from .config import EmulatorPresets, resolve_launch
from .custom import CustomCommandEmulator

#: Handy starting templates; users edit paths to match their install.
PRESETS: Dict[str, str] = {
    "retroarch": '"retroarch" -L "{CORE}" "{ROM}"',
    "project64": '"Project64.exe" "{ROM}"',
    "dolphin": '"Dolphin.exe" "{ROM}"',
    "pcsx2": '"pcsx2.exe" "{ROM}"',
    "duckstation": '"duckstation.exe" "{ROM}"',
    "rpcs3": '"rpcs3.exe" "{ROM}"',
    "xenia": '"xenia.exe" "{ROM}"',
    "custom": '"{ROM}"',
}

__all__ = ["EmulatorAdapter", "LaunchStatus", "CustomCommandEmulator",
           "EmulatorPresets", "resolve_launch", "PRESETS"]
