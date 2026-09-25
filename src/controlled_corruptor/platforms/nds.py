"""Nintendo DS platform adapter.

The NDS header is 0x200 bytes and carries a CRC-16 (poly 0xA001, init 0xFFFF)
over bytes 0x000..0x15D, stored at 0x15E. We detect an NDS image by that
self-consistent header CRC, protect the header, and can repair the CRC after
corruption.
"""

from __future__ import annotations

import struct
from typing import List

from ..core.regions import Region
from ..core.validation import Level, ValidationReport
from .base import PlatformAdapter

_HEADER_SIZE = 0x200
_CRC_RANGE_END = 0x15E   # CRC computed over [0x000, 0x15E)
_CRC_OFFSET = 0x15E


def crc16(data: bytes, init: int = 0xFFFF) -> int:
    """CRC-16 (reflected, poly 0xA001) as used by the NDS header."""
    crc = init
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


class NDSPlatform(PlatformAdapter):
    id = "nds"
    name = "Nintendo DS"
    priority = 45

    def _header_crc(self, data: bytes) -> int:
        return crc16(data[0:_CRC_RANGE_END])

    def detect(self, data: bytes) -> float:
        if len(data) < _HEADER_SIZE:
            return 0.0
        stored = struct.unpack_from("<H", data, _CRC_OFFSET)[0]
        if stored == self._header_crc(data):
            return 0.9  # self-consistent header CRC is a strong signal
        # Fallback weak signal: printable game code + unit code sane.
        gamecode = data[0x0C:0x10]
        if all(0x20 <= b < 0x7F for b in gamecode) and data[0x12] in (0, 2, 3):
            return 0.3
        return 0.0

    def endianness(self, data: bytes) -> str:
        return "little"

    def protected_regions(self, data: bytes) -> List[Region]:
        return [
            Region("NDS Header", 0x0, _HEADER_SIZE, category="header",
                   mutable=False, endianness="little", source="platform:nds",
                   description="Cartridge header (title, codes, offsets, CRCs)."),
        ]

    def repair_checksum(self, data: bytes) -> bytes:
        if len(data) < _HEADER_SIZE:
            return data
        out = bytearray(data)
        struct.pack_into("<H", out, _CRC_OFFSET, self._header_crc(bytes(out)))
        return bytes(out)

    def validate(self, data: bytes) -> ValidationReport:
        report = ValidationReport()
        if len(data) < _HEADER_SIZE:
            report.add("nds.header", Level.WARNING, "file smaller than an NDS header")
            return report
        stored = struct.unpack_from("<H", data, _CRC_OFFSET)[0]
        want = self._header_crc(data)
        if stored == want:
            report.add("nds.header_crc", Level.PASS, "header CRC matches")
        else:
            report.add("nds.header_crc", Level.WARNING,
                       f"header CRC mismatch (repairable): {stored:04X} != {want:04X}")
        return report

    def info(self, data: bytes) -> dict:
        info = {"platform": self.id, "name": self.name, "endianness": "little"}
        if len(data) >= _HEADER_SIZE:
            title = data[0x00:0x0C].split(b"\x00")[0]
            info["internal_title"] = title.decode("ascii", "replace").strip()
            info["game_code"] = data[0x0C:0x10].decode("ascii", "replace")
        return info
