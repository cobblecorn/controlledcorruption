"""Detection + header protection for disc and executable adapters."""

from __future__ import annotations

import struct

from controlled_corruptor import platforms
from controlled_corruptor.core.prng import Rng


def _pad(data: bytes, size: int) -> bytes:
    buf = bytearray(Rng("pad").randbytes(size))
    buf[:len(data)] = data
    return bytes(buf)


def test_gamecube_detect_and_protect():
    buf = bytearray(_pad(b"GALE01", 0x3000))
    struct.pack_into(">I", buf, 0x1C, 0xC2339F3D)
    adapter = platforms.detect(bytes(buf))
    assert adapter.id == "gamecube"
    prot = adapter.protected_regions(bytes(buf))
    assert prot[0].end == 0x2440


def test_wii_detect_and_warns_partitions():
    buf = bytearray(_pad(b"RSBE01", 0x3000))
    struct.pack_into(">I", buf, 0x18, 0x5D1C9EA3)
    adapter = platforms.detect(bytes(buf))
    assert adapter.id == "wii"
    levels = [c.level.value for c in adapter.validate(bytes(buf)).checks]
    assert "WARNING" in levels  # partition hash warning


def test_iso9660_detect_and_system_area_protected():
    buf = bytearray(0x9000)
    buf[0x8001:0x8006] = b"CD001"
    adapter = platforms.detect(bytes(buf))
    assert adapter.id == "iso9660"
    prot = adapter.protected_regions(bytes(buf))
    assert prot[0].start == 0 and prot[0].end == 0x8000


def test_iso9660_sony_licence_detected():
    buf = bytearray(0x9000)
    buf[0x8001:0x8006] = b"CD001"
    buf[0x100:0x100 + 27] = b"Sony Computer Entertainment"
    adapter = platforms.get("iso9660")
    info = adapter.info(bytes(buf))
    assert info["sony_licence"] is True


def test_psx_exe_detect():
    buf = _pad(b"PS-X EXE", 0x1000)
    adapter = platforms.detect(buf)
    assert adapter.id == "psx-exe"
    assert adapter.protected_regions(buf)[0].end == 0x800


def test_xex_detect_big_endian():
    buf = _pad(b"XEX2", 0x2000)
    adapter = platforms.detect(buf)
    assert adapter.id == "xex"
    assert adapter.endianness(buf) == "big"


def test_xbe_detect_little_endian():
    buf = _pad(b"XBEH", 0x2000)
    adapter = platforms.detect(buf)
    assert adapter.id == "xbe"
    assert adapter.endianness(buf) == "little"


def test_all_registered():
    ids = set(platforms.available())
    assert {"gamecube", "wii", "iso9660", "psx-exe", "xex", "xbe"} <= ids


def test_repair_is_noop_for_headerless_formats():
    # these adapters have no global checksum; repair must be a safe no-op
    buf = _pad(b"XBEH", 0x2000)
    adapter = platforms.get("xbe")
    assert adapter.repair_checksum(buf) == buf
