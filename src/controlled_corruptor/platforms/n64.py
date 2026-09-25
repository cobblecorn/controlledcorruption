"""Nintendo 64 platform adapter.

Understands the three common byte orders and, crucially, can **repair the ROM
checksum** after corruption so a mutated ROM still passes the boot integrity
check. This demonstrates the "checksum repair as a platform service" design:
the maths lives here, not in the mutation engine.

The CRC algorithm is the well-known N64 CIC checksum (compatible with tools
like ``n64crc``), supporting CIC 6101/6102/6103/6105/6106.
"""

from __future__ import annotations

import binascii
import struct
from typing import List, Optional

from ..core.regions import Region
from ..core.validation import Level, ValidationReport
from .base import PlatformAdapter

# Byte-order magic in the first 4 bytes.
_MAGIC_Z64 = b"\x80\x37\x12\x40"  # big-endian, native
_MAGIC_V64 = b"\x37\x80\x40\x12"  # byteswapped (16-bit)
_MAGIC_N64 = b"\x40\x12\x37\x80"  # little-endian (32-bit)

_HEADER_SIZE = 0x40
_BC_SIZE = 0x1000 - _HEADER_SIZE
_CHECKSUM_START = 0x1000
_CHECKSUM_LENGTH = 0x100000
_MASK32 = 0xFFFFFFFF

# CIC seeds
_SEED = {
    6101: 0xF8CA4DDC,
    6102: 0xF8CA4DDC,
    6103: 0xA3886759,
    6105: 0xDF26F436,
    6106: 0x1FEA617A,
}


def _rol(value: int, bits: int) -> int:
    bits &= 31
    return ((value << bits) | (value >> (32 - bits))) & _MASK32


def _u32be(data: bytes, off: int) -> int:
    return struct.unpack_from(">I", data, off)[0]


def _to_z64(data: bytes, fmt: str) -> bytes:
    """Normalize any byte order to big-endian (.z64)."""
    if fmt == "z64":
        return data
    b = bytearray(data)
    if fmt == "v64":  # swap adjacent byte pairs
        b[: len(b) - (len(b) % 2)] = b"".join(
            bytes((b[i + 1], b[i])) for i in range(0, len(b) - 1, 2)
        )
    elif fmt == "n64":  # reverse each 4-byte word
        n = len(b) - (len(b) % 4)
        b[:n] = b"".join(bytes(reversed(b[i:i + 4])) for i in range(0, n, 4))
    return bytes(b)


class N64Platform(PlatformAdapter):
    id = "n64"
    name = "Nintendo 64"
    priority = 50

    # -- identification -----------------------------------------------------
    def _format(self, data: bytes) -> Optional[str]:
        head = data[:4]
        if head == _MAGIC_Z64:
            return "z64"
        if head == _MAGIC_V64:
            return "v64"
        if head == _MAGIC_N64:
            return "n64"
        return None

    def detect(self, data: bytes) -> float:
        if len(data) < 0x1000:
            return 0.0
        return 0.95 if self._format(data) else 0.0

    def endianness(self, data: bytes) -> str:
        return "big"

    # -- structure ----------------------------------------------------------
    def protected_regions(self, data: bytes) -> List[Region]:
        return [
            Region("N64 Header", 0x0, _HEADER_SIZE, category="header",
                   mutable=False, endianness="big", source="platform:n64",
                   description="ROM header (title, CRC words, media/config)."),
            Region("N64 Boot Code", _HEADER_SIZE, 0x1000, category="executable",
                   mutable=False, endianness="big", source="platform:n64",
                   description="IPL3 boot code; corrupting it prevents boot."),
        ]

    # -- checksum -----------------------------------------------------------
    def _detect_cic(self, z64: bytes) -> int:
        crc = binascii.crc32(z64[_HEADER_SIZE:_HEADER_SIZE + _BC_SIZE]) & _MASK32
        return {
            0x6170A4A1: 6101,
            0x90BB6CB5: 6102,
            0x0B050EE0: 6103,
            0x98BC2C86: 6105,
            0xACC8580A: 6106,
        }.get(crc, 6102)

    def calc_crc(self, z64: bytes) -> tuple:
        """Return the (crc1, crc2) pair for a big-endian ROM image."""
        cic = self._detect_cic(z64)
        seed = _SEED[cic]
        t1 = t2 = t3 = t4 = t5 = t6 = seed

        i = _CHECKSUM_START
        end = _CHECKSUM_START + _CHECKSUM_LENGTH
        while i < end:
            d = _u32be(z64, i)
            if ((t6 + d) & _MASK32) < t6:
                t4 = (t4 + 1) & _MASK32
            t6 = (t6 + d) & _MASK32
            t3 ^= d
            r = _rol(d, d & 0x1F)
            t5 = (t5 + r) & _MASK32
            if t2 > d:
                t2 ^= r
            else:
                t2 ^= t6 ^ d
            if cic == 6105:
                off = _HEADER_SIZE + 0x0710 + (i & 0xFF)
                t1 = (t1 + (_u32be(z64, off) ^ d)) & _MASK32
            else:
                t1 = (t1 + (t5 ^ d)) & _MASK32
            i += 4

        if cic == 6103:
            crc1 = ((t6 ^ t4) + t3) & _MASK32
            crc2 = ((t5 ^ t2) + t1) & _MASK32
        elif cic == 6106:
            crc1 = ((t6 * t4) + t3) & _MASK32
            crc2 = ((t5 * t2) + t1) & _MASK32
        else:
            crc1 = (t6 ^ t4 ^ t3) & _MASK32
            crc2 = (t5 ^ t2 ^ t1) & _MASK32
        return crc1, crc2

    def repair_checksum(self, data: bytes) -> bytes:
        fmt = self._format(data)
        if fmt is None or len(data) < _CHECKSUM_START + _CHECKSUM_LENGTH:
            return data  # not a recognizable / large-enough N64 ROM
        z64 = bytearray(_to_z64(data, fmt))
        crc1, crc2 = self.calc_crc(bytes(z64))
        struct.pack_into(">I", z64, 0x10, crc1)
        struct.pack_into(">I", z64, 0x14, crc2)
        # Convert back to the original byte order (swaps are self-inverse).
        return _to_z64(bytes(z64), fmt)

    # -- validation ---------------------------------------------------------
    def validate(self, data: bytes) -> ValidationReport:
        report = ValidationReport()
        fmt = self._format(data)
        if fmt is None:
            report.add("n64.header", Level.WARNING, "no recognizable N64 magic")
            return report
        report.add("n64.format", Level.PASS, f"byte order: {fmt}")
        if len(data) >= _CHECKSUM_START + _CHECKSUM_LENGTH:
            z64 = _to_z64(data, fmt)
            crc1, crc2 = self.calc_crc(z64)
            stored1, stored2 = _u32be(z64, 0x10), _u32be(z64, 0x14)
            if (crc1, crc2) == (stored1, stored2):
                report.add("n64.checksum", Level.PASS, "checksum matches")
            else:
                report.add("n64.checksum", Level.WARNING,
                           f"checksum mismatch (repairable): stored "
                           f"{stored1:08X}{stored2:08X} != {crc1:08X}{crc2:08X}")
        return report

    def info(self, data: bytes) -> dict:
        fmt = self._format(data)
        info = {"platform": self.id, "name": self.name,
                "endianness": "big", "byte_order": fmt}
        if fmt and len(data) >= 0x40:
            z64 = _to_z64(data, fmt)
            title = z64[0x20:0x34].split(b"\x00")[0]
            try:
                info["internal_title"] = title.decode("ascii", "replace").strip()
            except Exception:
                info["internal_title"] = repr(title)
            info["cic"] = self._detect_cic(z64) if len(z64) >= 0x1000 else None
        return info
