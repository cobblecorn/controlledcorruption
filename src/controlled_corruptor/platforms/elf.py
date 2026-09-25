"""ELF executable adapter (PS2/PSP homebrew, many console SDKs, Linux).

Parses the ELF header (class + endianness aware) and protects the header plus
the program-header and section-header tables, leaving code/data corruptible.
"""

from __future__ import annotations

import struct
from typing import List, Optional

from ..core.regions import Region
from ..core.validation import Level, ValidationReport
from .base import PlatformAdapter

_MAGIC = b"\x7fELF"


class ELFPlatform(PlatformAdapter):
    id = "elf"
    name = "ELF Executable"
    priority = 30

    def _parse(self, data: bytes) -> Optional[dict]:
        if len(data) < 0x34 or data[:4] != _MAGIC:
            return None
        ei_class = data[4]      # 1=32, 2=64
        ei_data = data[5]       # 1=little, 2=big
        if ei_class not in (1, 2) or ei_data not in (1, 2):
            return None
        e = "<" if ei_data == 1 else ">"
        try:
            if ei_class == 1:
                (e_phoff,) = struct.unpack_from(e + "I", data, 0x1C)
                (e_shoff,) = struct.unpack_from(e + "I", data, 0x20)
                e_ehsize, e_phentsize, e_phnum, e_shentsize, e_shnum = \
                    struct.unpack_from(e + "HHHHH", data, 0x28)
            else:
                (e_phoff,) = struct.unpack_from(e + "Q", data, 0x20)
                (e_shoff,) = struct.unpack_from(e + "Q", data, 0x28)
                e_ehsize, e_phentsize, e_phnum, e_shentsize, e_shnum = \
                    struct.unpack_from(e + "HHHHH", data, 0x34)
        except struct.error:
            return None
        return {
            "class": 64 if ei_class == 2 else 32,
            "endian": "little" if ei_data == 1 else "big",
            "ehsize": e_ehsize, "phoff": e_phoff, "phentsize": e_phentsize,
            "phnum": e_phnum, "shoff": e_shoff, "shentsize": e_shentsize,
            "shnum": e_shnum,
        }

    def detect(self, data: bytes) -> float:
        return 0.9 if self._parse(data) else 0.0

    def endianness(self, data: bytes) -> str:
        info = self._parse(data)
        return info["endian"] if info else "little"

    def protected_regions(self, data: bytes) -> List[Region]:
        info = self._parse(data)
        if not info:
            return []
        size = len(data)
        regions = [Region("ELF Header", 0x0, min(size, max(info["ehsize"], 0x34)),
                          category="header", mutable=False, endianness=info["endian"],
                          source="platform:elf", description="ELF file header.")]
        if info["phnum"] and info["phoff"]:
            end = info["phoff"] + info["phnum"] * info["phentsize"]
            if end <= size:
                regions.append(Region("ELF Program Headers", info["phoff"], end,
                                      category="header", mutable=False,
                                      endianness=info["endian"], source="platform:elf"))
        if info["shnum"] and info["shoff"]:
            end = info["shoff"] + info["shnum"] * info["shentsize"]
            if end <= size:
                regions.append(Region("ELF Section Headers", info["shoff"], end,
                                      category="header", mutable=False,
                                      endianness=info["endian"], source="platform:elf"))
        return regions

    def validate(self, data: bytes) -> ValidationReport:
        report = ValidationReport()
        info = self._parse(data)
        if info:
            report.add("elf.header", Level.PASS,
                       f"ELF{info['class']} {info['endian']}-endian, "
                       f"{info['phnum']} segments, {info['shnum']} sections")
        else:
            report.add("elf.header", Level.WARNING, "not a valid ELF header")
        return report

    def info(self, data: bytes) -> dict:
        parsed = self._parse(data)
        out = {"platform": self.id, "name": self.name}
        if parsed:
            out.update({"class": parsed["class"], "endianness": parsed["endian"],
                        "segments": parsed["phnum"], "sections": parsed["shnum"]})
        return out
