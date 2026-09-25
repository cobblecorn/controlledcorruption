"""Lightweight validation results.

Validation is advisory. This is a corruption tool -- weird output is the point
-- so validators report PASS / WARNING / FAIL but never block by default.
Platforms and profiles can contribute checks (header valid, checksum valid,
known section lengths, ...).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List


class Level(str, Enum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"


@dataclass
class Check:
    name: str
    level: Level
    message: str = ""

    def __str__(self) -> str:
        return f"[{self.level.value}] {self.name}: {self.message}".rstrip(": ")


@dataclass
class ValidationReport:
    checks: List[Check] = field(default_factory=list)

    def add(self, name: str, level: Level, message: str = "") -> None:
        self.checks.append(Check(name, level, message))

    @property
    def worst(self) -> Level:
        if any(c.level == Level.FAIL for c in self.checks):
            return Level.FAIL
        if any(c.level == Level.WARNING for c in self.checks):
            return Level.WARNING
        return Level.PASS

    def to_dict(self) -> dict:
        return {
            "worst": self.worst.value,
            "checks": [
                {"name": c.name, "level": c.level.value, "message": c.message}
                for c in self.checks
            ],
        }
