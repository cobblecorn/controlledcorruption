"""GBA and NDS adapter detection, protection and checksum repair."""

from __future__ import annotations

import struct

from controlled_corruptor import platforms
from controlled_corruptor.core.prng import Rng
from controlled_corruptor.core.validation import Level
from controlled_corruptor.platforms.gba import GBAPlatform, _LOGO_MAGIC
from controlled_corruptor.platforms.nds import NDSPlatform, crc16


def _fake_gba() -> bytes:
    rng = Rng("gba")
    buf = bytearray(rng.randbytes(0x400))
    buf[0x04:0x04 + len(_LOGO_MAGIC)] = _LOGO_MAGIC
    buf[0xB2] = 0x96
    buf[0xA0:0xAC] = b"TESTGAME\x00\x00\x00\x00"
    return GBAPlatform().repair_checksum(bytes(buf))


def _fake_nds() -> bytes:
    rng = Rng("nds")
    buf = bytearray(rng.randbytes(0x8000))
    buf[0x00:0x0C] = b"TESTDS\x00\x00\x00\x00\x00\x00"
    buf[0x0C:0x10] = b"ADSE"
    buf[0x12] = 0
    return NDSPlatform().repair_checksum(bytes(buf))


def test_gba_detected_and_repaired():
    rom = _fake_gba()
    assert platforms.detect(rom).id == "gba"
    gba = GBAPlatform()
    report = gba.validate(rom)
    levels = {c.name: c.level for c in report.checks}
    assert levels.get("gba.checksum") == Level.PASS
    assert levels.get("gba.logo") == Level.PASS


def test_gba_repair_idempotent():
    gba = GBAPlatform()
    rom = _fake_gba()
    assert gba.repair_checksum(rom) == rom


def test_gba_protects_header():
    prot = GBAPlatform().protected_regions(_fake_gba())
    assert prot and prot[0].start == 0 and prot[0].end == 0xC0


def test_nds_detected_and_repaired():
    rom = _fake_nds()
    assert platforms.detect(rom).id == "nds"
    report = NDSPlatform().validate(rom)
    levels = {c.name: c.level for c in report.checks}
    assert levels.get("nds.header_crc") == Level.PASS


def test_nds_repair_idempotent():
    nds = NDSPlatform()
    rom = _fake_nds()
    assert nds.repair_checksum(rom) == rom


def test_crc16_known_vector():
    # CRC-16/MODBUS of "123456789" is 0x4B37
    assert crc16(b"123456789") == 0x4B37


def test_info_titles():
    assert GBAPlatform().info(_fake_gba())["internal_title"].startswith("TESTGAME")
    assert NDSPlatform().info(_fake_nds())["internal_title"].startswith("TESTDS")


def test_non_matching_falls_back_to_generic():
    assert platforms.detect(b"\x00" * 0x400).id == "generic"
