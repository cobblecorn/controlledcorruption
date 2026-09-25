"""Console-executable adapters: PlayStation PS-X EXE, Xbox XEX/XBE.

These are magic-identified executable containers. We protect the header so the
loader still recognizes the file, leaving the code/data body corruptible. No
global checksum repair is required for these formats to load in emulators
(individual sections may have their own integrity fields, which is future work).
"""

from __future__ import annotations

from typing import List

from ..core.regions import Region
from ..core.validation import Level, ValidationReport
from .base import PlatformAdapter


class _MagicExecutable(PlatformAdapter):
    magic = b""
    header_size = 0x100
    endian = "little"

    def detect(self, data: bytes) -> float:
        if len(data) < len(self.magic):
            return 0.0
        return 0.95 if data[:len(self.magic)] == self.magic else 0.0

    def endianness(self, data: bytes) -> str:
        return self.endian

    def protected_regions(self, data: bytes) -> List[Region]:
        return [Region(f"{self.name} Header", 0x0, self.header_size,
                       category="header", mutable=False, endianness=self.endian,
                       source=f"platform:{self.id}",
                       description="Executable header (entry point, section table).")]

    def validate(self, data: bytes) -> ValidationReport:
        report = ValidationReport()
        if data[:len(self.magic)] == self.magic:
            report.add(f"{self.id}.magic", Level.PASS,
                       f"{self.magic!r} magic present")
        else:
            report.add(f"{self.id}.magic", Level.WARNING, "magic missing")
        return report


class PSXEXEPlatform(_MagicExecutable):
    id = "psx-exe"
    name = "PlayStation Executable"
    magic = b"PS-X EXE"
    header_size = 0x800
    endian = "little"
    priority = 60


class XEXPlatform(_MagicExecutable):
    """Xbox 360 executable (XEX2)."""

    id = "xex"
    name = "Xbox 360 Executable"
    magic = b"XEX2"
    header_size = 0x1000
    endian = "big"  # 360 is big-endian (PowerPC)
    priority = 60


class XBEPlatform(_MagicExecutable):
    """Original Xbox executable (XBEH)."""

    id = "xbe"
    name = "Xbox Executable"
    magic = b"XBEH"
    header_size = 0x1000
    endian = "little"  # original Xbox is x86 little-endian
    priority = 60
