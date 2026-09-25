"""Generic ISO9660 optical-disc adapter (covers many PS1/PS2/PSP images).

Detects an ISO9660 filesystem by the ``CD001`` identifier of the primary volume
descriptor at sector 16 (offset 0x8000 in a 2048-byte/sector image) and
protects the 16-sector system area, which holds boot/licence data. This is the
pragmatic, format-agnostic way to corrupt disc images safely without decoding
every console's disc structure.
"""

from __future__ import annotations

from typing import List

from ..core.regions import Region
from ..core.validation import Level, ValidationReport
from .base import PlatformAdapter

_PVD_OFFSET = 0x8000       # sector 16 for 2048-byte sectors
_SYSTEM_AREA_END = 0x8000  # first 16 sectors are the system area
_ID = b"CD001"


class ISO9660Platform(PlatformAdapter):
    id = "iso9660"
    name = "ISO9660 Disc Image"
    priority = 10  # low; a specific console adapter should win if it also matches

    def detect(self, data: bytes) -> float:
        if len(data) < _PVD_OFFSET + 6:
            return 0.0
        # Volume descriptor: type byte then "CD001".
        if data[_PVD_OFFSET + 1:_PVD_OFFSET + 6] == _ID:
            return 0.6
        return 0.0

    def protected_regions(self, data: bytes) -> List[Region]:
        return [Region("ISO System Area", 0x0, _SYSTEM_AREA_END, category="header",
                       mutable=False, source="platform:iso9660",
                       description="16-sector system area (boot/licence).")]

    def _has_sony_licence(self, data: bytes) -> bool:
        return b"Sony Computer Entertainment" in data[:_SYSTEM_AREA_END]

    def validate(self, data: bytes) -> ValidationReport:
        report = ValidationReport()
        if len(data) >= _PVD_OFFSET + 6 and data[_PVD_OFFSET + 1:_PVD_OFFSET + 6] == _ID:
            report.add("iso9660.pvd", Level.PASS, "ISO9660 primary volume descriptor found")
            if self._has_sony_licence(data):
                report.add("iso9660.sony", Level.PASS,
                           "Sony licence string present (PS1/PS2 disc)")
        else:
            report.add("iso9660.pvd", Level.WARNING, "no ISO9660 volume descriptor")
        return report

    def info(self, data: bytes) -> dict:
        info = {"platform": self.id, "name": self.name}
        if len(data) >= _PVD_OFFSET + 40:
            vol_id = data[_PVD_OFFSET + 40:_PVD_OFFSET + 72].split(b"\x00")[0]
            info["volume_id"] = vol_id.decode("ascii", "replace").strip()
            info["sony_licence"] = self._has_sony_licence(data)
        return info
