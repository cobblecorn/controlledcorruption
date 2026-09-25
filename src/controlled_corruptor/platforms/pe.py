"""PE executable adapter (Windows / many PC game binaries).

Protects the DOS header, PE signature, COFF + optional header, and the section
table, leaving section bodies (code/data/resources) corruptible.
"""

from __future__ import annotations

import struct
from typing import List, Optional

from ..core.regions import Region
from ..core.validation import Level, ValidationReport
from .base import PlatformAdapter


class PEPlatform(PlatformAdapter):
    id = "pe"
    name = "PE Executable"
    priority = 30

    def _parse(self, data: bytes) -> Optional[dict]:
        if len(data) < 0x40 or data[:2] != b"MZ":
            return None
        (e_lfanew,) = struct.unpack_from("<I", data, 0x3C)
        if e_lfanew + 24 > len(data):
            return None
        if data[e_lfanew:e_lfanew + 4] != b"PE\x00\x00":
            return None
        num_sections, = struct.unpack_from("<H", data, e_lfanew + 6)
        opt_size, = struct.unpack_from("<H", data, e_lfanew + 20)
        headers_end = e_lfanew + 24 + opt_size + num_sections * 40
        return {"lfanew": e_lfanew, "num_sections": num_sections,
                "opt_size": opt_size, "headers_end": headers_end}

    def detect(self, data: bytes) -> float:
        return 0.9 if self._parse(data) else 0.0

    def endianness(self, data: bytes) -> str:
        return "little"

    def protected_regions(self, data: bytes) -> List[Region]:
        info = self._parse(data)
        if not info:
            return []
        end = min(len(data), info["headers_end"])
        return [Region("PE Headers", 0x0, end, category="header", mutable=False,
                       endianness="little", source="platform:pe",
                       description="DOS + PE + optional header + section table.")]

    def validate(self, data: bytes) -> ValidationReport:
        report = ValidationReport()
        info = self._parse(data)
        if info:
            report.add("pe.header", Level.PASS,
                       f"PE with {info['num_sections']} sections")
        else:
            report.add("pe.header", Level.WARNING, "not a valid PE header")
        return report

    def info(self, data: bytes) -> dict:
        info = self._parse(data)
        out = {"platform": self.id, "name": self.name, "endianness": "little"}
        if info:
            out["sections"] = info["num_sections"]
        return out
