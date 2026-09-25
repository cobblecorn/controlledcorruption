"""Persisted emulator presets.

Users configure emulator launch commands once and reference them by name (e.g.
``--launch @dolphin``). Stored as JSON under the config dir, overridable with
``CCORRUPT_CONFIG_DIR`` (which also makes it testable).
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

from .custom import CustomCommandEmulator


def config_dir() -> str:
    override = os.environ.get("CCORRUPT_CONFIG_DIR")
    if override:
        return override
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = xdg or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "ccorrupt")


def presets_path() -> str:
    return os.path.join(config_dir(), "emulators.json")


class EmulatorPresets:
    def __init__(self, path: Optional[str] = None):
        self.path = path or presets_path()
        self.data: Dict = {"emulators": {}, "default": None}
        self.load()

    # -- persistence --------------------------------------------------------
    def load(self) -> None:
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                self.data = {
                    "emulators": dict(loaded.get("emulators", {})),
                    "default": loaded.get("default"),
                }
        except (FileNotFoundError, ValueError):
            pass

    def save(self) -> str:
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, indent=2)
        return self.path

    # -- CRUD ---------------------------------------------------------------
    def add(self, name: str, command: str, *, working_dir: Optional[str] = None,
            timeout: Optional[float] = None, make_default: bool = False) -> None:
        self.data["emulators"][name] = {
            "command": command, "working_dir": working_dir, "timeout": timeout}
        if make_default or self.data.get("default") is None:
            self.data["default"] = name

    def remove(self, name: str) -> bool:
        existed = name in self.data["emulators"]
        self.data["emulators"].pop(name, None)
        if self.data.get("default") == name:
            remaining = self.names()
            self.data["default"] = remaining[0] if remaining else None
        return existed

    def get(self, name: str) -> Optional[dict]:
        return self.data["emulators"].get(name)

    def names(self) -> List[str]:
        return sorted(self.data["emulators"])

    def default(self) -> Optional[str]:
        return self.data.get("default")

    def set_default(self, name: str) -> None:
        if name not in self.data["emulators"]:
            raise KeyError(f"no such preset {name!r}")
        self.data["default"] = name

    # -- resolution ---------------------------------------------------------
    def resolve_command(self, name: str) -> str:
        entry = self.get(name)
        if entry is None:
            raise KeyError(f"no emulator preset named {name!r}; "
                           f"have: {', '.join(self.names()) or '(none)'}")
        return entry["command"]

    def make_adapter(self, name: str) -> CustomCommandEmulator:
        entry = self.get(name)
        if entry is None:
            raise KeyError(f"no emulator preset named {name!r}")
        return CustomCommandEmulator(entry["command"], name=name,
                                     working_dir=entry.get("working_dir"),
                                     timeout=entry.get("timeout"))


def resolve_launch(value: str, presets: Optional[EmulatorPresets] = None) -> str:
    """Resolve a ``--launch`` value: ``@name`` -> preset command, else verbatim."""
    if value and value.startswith("@"):
        presets = presets or EmulatorPresets()
        return presets.resolve_command(value[1:])
    return value
