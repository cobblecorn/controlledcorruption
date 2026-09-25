"""GameCube and Wii optical-disc adapters.

Both are identified by a magic word in the disc header. We protect the disc
header (and, for Wii, the region past it is partition/hash protected on real
hardware -- corrupting a data partition breaks its per-block hashes, so Wii
corruption is best kept to whole non-critical files; that structural awareness
is a future enhancement).
"""

from __future__ import annotations

import struct
from typing import List

from ..core.regions import Region
from ..core.validation import Level, ValidationReport
from .base import PlatformAdapter

_GC_MAGIC = 0xC2339F3D   # at 0x1C
_WII_MAGIC = 0x5D1C9EA3  # at 0x18


def _u32be(data: bytes, off: int) -> int:
    return struct.unpack_from(">I", data, off)[0]


class GameCubePlatform(PlatformAdapter):
    id = "gamecube"
    name = "Nintendo GameCube"
    priority = 55

    def detect(self, data: bytes) -> float:
        if len(data) < 0x20:
            return 0.0
        return 0.95 if _u32be(data, 0x1C) == _GC_MAGIC else 0.0

    def endianness(self, data: bytes) -> str:
        return "big"

    def protected_regions(self, data: bytes) -> List[Region]:
        return [Region("GC Disc Header", 0x0, 0x2440, category="header",
                       mutable=False, endianness="big", source="platform:gamecube",
                       description="Disc header + apploader region.")]

    def validate(self, data: bytes) -> ValidationReport:
        report = ValidationReport()
        if len(data) >= 0x20 and _u32be(data, 0x1C) == _GC_MAGIC:
            report.add("gamecube.magic", Level.PASS, "GameCube disc magic present")
        else:
            report.add("gamecube.magic", Level.WARNING, "GameCube magic missing")
        return report

    def info(self, data: bytes) -> dict:
        info = {"platform": self.id, "name": self.name, "endianness": "big"}
        if len(data) >= 0x20:
            info["game_id"] = data[0x0:0x6].decode("ascii", "replace")
            info["internal_title"] = data[0x20:0x60].split(b"\x00")[0].decode("ascii", "replace")
        return info


class WiiPlatform(PlatformAdapter):
    id = "wii"
    name = "Nintendo Wii"
    priority = 55

    def detect(self, data: bytes) -> float:
        if len(data) < 0x20:
            return 0.0
        return 0.95 if _u32be(data, 0x18) == _WII_MAGIC else 0.0

    def endianness(self, data: bytes) -> str:
        return "big"

    def protected_regions(self, data: bytes) -> List[Region]:
        return [Region("Wii Disc Header", 0x0, 0x2440, category="header",
                       mutable=False, endianness="big", source="platform:wii",
                       description="Disc header. NOTE: data partitions are hash "
                                   "protected; corrupting them breaks per-block hashes.")]

    def validate(self, data: bytes) -> ValidationReport:
        report = ValidationReport()
        if len(data) >= 0x20 and _u32be(data, 0x18) == _WII_MAGIC:
            report.add("wii.magic", Level.PASS, "Wii disc magic present")
            report.add("wii.partitions", Level.WARNING,
                       "data partitions are hash-protected; expect boot failures "
                       "if you corrupt inside them")
        else:
            report.add("wii.magic", Level.WARNING, "Wii magic missing")
        return report

    def info(self, data: bytes) -> dict:
        info = {"platform": self.id, "name": self.name, "endianness": "big"}
        if len(data) >= 0x60:
            info["game_id"] = data[0x0:0x6].decode("ascii", "replace")
            info["internal_title"] = data[0x20:0x60].split(b"\x00")[0].decode("ascii", "replace")
        return info
