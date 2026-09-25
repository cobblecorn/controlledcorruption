"""Platform adapter base class.

A platform adapter understands the *structure* of a family of files -- header,
endianness, which regions must be protected, and how to repair checksums after
mutation. It deliberately knows nothing about specific games (that is a
profile's job) and nothing about how mutations work (that is the engine's job).

Checksum repair is exposed as a platform service so the logic lives in one
place instead of being scattered through the mutation engine.
"""

from __future__ import annotations

from typing import List, Optional

from ..core.regions import Region
from ..core.validation import Level, ValidationReport


class PlatformAdapter:
    id: str = "base"
    name: str = "Base Platform"
    #: higher wins when several adapters match; Generic uses a low value.
    priority: int = 0

    # -- identification -----------------------------------------------------
    def detect(self, data: bytes) -> float:
        """Return a confidence in [0, 1] that ``data`` is this platform."""
        return 0.0

    # -- structure ----------------------------------------------------------
    def endianness(self, data: bytes) -> str:
        return "little"

    def protected_regions(self, data: bytes) -> List[Region]:
        """Regions that must never be mutated for this platform (headers, boot)."""
        return []

    def known_regions(self, data: bytes) -> List[Region]:
        """Structural regions the adapter can identify without a game profile."""
        return []

    # -- services -----------------------------------------------------------
    def repair_checksum(self, data: bytes) -> bytes:
        """Return ``data`` with any platform checksums recomputed. Default no-op."""
        return data

    def validate(self, data: bytes) -> ValidationReport:
        report = ValidationReport()
        report.add(self.id, Level.PASS, "no platform-specific checks")
        return report

    def info(self, data: bytes) -> dict:
        return {"platform": self.id, "name": self.name,
                "endianness": self.endianness(data)}

    def normalize_output_ext(self, source_ext: Optional[str]) -> Optional[str]:
        """Optionally override the output file extension. Default: keep source."""
        return source_ext
