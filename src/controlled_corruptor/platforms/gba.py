"""Game Boy Advance platform adapter.

GBA ROMs begin with a 192-byte header: a 4-byte ARM branch, the 156-byte
Nintendo logo, a 12-byte title, codes, and a header checksum at 0xBD computed
over 0xA0..0xBC. We protect the header and can repair that checksum so a
corrupted ROM still passes the (soft) header check.
"""

from __future__ import annotations

from typing import List

from ..core.regions import Region
from ..core.validation import Level, ValidationReport
from .base import PlatformAdapter

_HEADER_END = 0xC0
_LOGO_START = 0x04
_LOGO_END = 0xA0
_CHK_START = 0xA0
_CHK_END = 0xBD  # bytes 0xA0..0xBC inclusive feed the checksum
_CHK_OFFSET = 0xBD

# First few bytes of the compressed Nintendo logo present in every GBA ROM.
_LOGO_MAGIC = bytes.fromhex("24ffae51699aa2")


class GBAPlatform(PlatformAdapter):
    id = "gba"
    name = "Game Boy Advance"
    priority = 40

    def detect(self, data: bytes) -> float:
        if len(data) < _HEADER_END:
            return 0.0
        # The fixed value 0x96 at 0xB2, plus the logo magic, is a strong signal.
        score = 0.0
        if data[0xB2] == 0x96:
            score += 0.5
        if data[_LOGO_START:_LOGO_START + len(_LOGO_MAGIC)] == _LOGO_MAGIC:
            score += 0.45
        return score

    def endianness(self, data: bytes) -> str:
        return "little"

    def protected_regions(self, data: bytes) -> List[Region]:
        return [
            Region("GBA Header", 0x0, _HEADER_END, category="header",
                   mutable=False, endianness="little", source="platform:gba",
                   description="Entry point, Nintendo logo, title, header checksum."),
        ]

    def _header_checksum(self, data: bytes) -> int:
        chk = 0
        for i in range(_CHK_START, _CHK_END):
            chk = (chk - data[i]) & 0xFF
        return (chk - 0x19) & 0xFF

    def repair_checksum(self, data: bytes) -> bytes:
        if len(data) < _HEADER_END:
            return data
        out = bytearray(data)
        out[_CHK_OFFSET] = self._header_checksum(out)
        return bytes(out)

    def validate(self, data: bytes) -> ValidationReport:
        report = ValidationReport()
        if len(data) < _HEADER_END:
            report.add("gba.header", Level.WARNING, "file smaller than a GBA header")
            return report
        if data[_LOGO_START:_LOGO_START + len(_LOGO_MAGIC)] == _LOGO_MAGIC:
            report.add("gba.logo", Level.PASS, "Nintendo logo present")
        else:
            report.add("gba.logo", Level.WARNING, "Nintendo logo missing/corrupt")
        want = self._header_checksum(data)
        if data[_CHK_OFFSET] == want:
            report.add("gba.checksum", Level.PASS, "header checksum matches")
        else:
            report.add("gba.checksum", Level.WARNING,
                       f"header checksum mismatch (repairable): "
                       f"{data[_CHK_OFFSET]:02X} != {want:02X}")
        return report

    def info(self, data: bytes) -> dict:
        info = {"platform": self.id, "name": self.name, "endianness": "little"}
        if len(data) >= _HEADER_END:
            title = data[0xA0:0xAC].split(b"\x00")[0]
            info["internal_title"] = title.decode("ascii", "replace").strip()
            info["game_code"] = data[0xAC:0xB0].decode("ascii", "replace")
        return info
