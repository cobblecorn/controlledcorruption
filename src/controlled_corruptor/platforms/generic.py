"""Generic platform adapter -- matches any file at the lowest priority.

Provides no structural knowledge; the whole file is fair game (minus whatever
the user marks protected). This is what powers "Generic Mode" for arbitrary
.bin/.dat/.pak/etc files.
"""

from __future__ import annotations

from typing import List

from ..core.regions import Region
from ..core.validation import Level, ValidationReport
from .base import PlatformAdapter


class GenericPlatform(PlatformAdapter):
    id = "generic"
    name = "Generic Binary"
    priority = -100  # always the fallback

    def detect(self, data: bytes) -> float:
        return 0.01  # matches everything, but only when nothing else does

    def protected_regions(self, data: bytes) -> List[Region]:
        return []

    def validate(self, data: bytes) -> ValidationReport:
        report = ValidationReport()
        report.add("generic", Level.PASS, f"{len(data)} bytes, no structure assumed")
        return report
