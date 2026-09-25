"""Platform detection, N64 checksum repair, and generic fallback."""

from __future__ import annotations


from controlled_corruptor import platforms
from controlled_corruptor.core.prng import Rng
from controlled_corruptor.core.validation import Level
from controlled_corruptor.demo import build_demo_rom
from controlled_corruptor.platforms.n64 import N64Platform, _to_z64


def _fake_n64(order="z64") -> bytes:
    size = 0x1000 + 0x100000 + 0x1000
    rng = Rng("fake-n64")
    buf = bytearray(rng.randbytes(size))
    buf[0:4] = {"z64": b"\x80\x37\x12\x40",
                "v64": b"\x37\x80\x40\x12",
                "n64": b"\x40\x12\x37\x80"}[order]
    return bytes(buf)


def test_generic_matches_arbitrary():
    adapter = platforms.detect(b"\x00\x01\x02\x03 not a rom")
    assert adapter.id == "generic"


def test_n64_detected():
    adapter = platforms.detect(_fake_n64("z64"))
    assert adapter.id == "n64"


def test_n64_protected_regions_cover_header_and_boot():
    n64 = N64Platform()
    prot = n64.protected_regions(_fake_n64())
    covered = set()
    for r in prot:
        covered.update(range(r.start, r.end))
    assert 0 in covered
    assert 0xFFF in covered  # boot code protected up to 0x1000


def test_n64_checksum_repair_then_validate_passes():
    n64 = N64Platform()
    rom = _fake_n64("z64")
    fixed = n64.repair_checksum(rom)
    report = n64.validate(fixed)
    checks = {c.name: c.level for c in report.checks}
    assert checks.get("n64.checksum") == Level.PASS


def test_n64_repair_is_idempotent():
    n64 = N64Platform()
    fixed = n64.repair_checksum(_fake_n64("z64"))
    assert n64.repair_checksum(fixed) == fixed


def test_n64_byte_order_conversions_self_inverse():
    rom = _fake_n64("z64")
    assert _to_z64(_to_z64(rom, "v64"), "v64") == rom
    assert _to_z64(_to_z64(rom, "n64"), "n64") == rom


def test_n64_repair_preserves_byte_order_and_size():
    n64 = N64Platform()
    for order in ("z64", "v64", "n64"):
        rom = _fake_n64(order)
        fixed = n64.repair_checksum(rom)
        assert len(fixed) == len(rom)
        assert fixed[0:4] == rom[0:4]  # magic (byte order) unchanged


def test_demo_rom_is_recognized_n64():
    rom = build_demo_rom()
    adapter = platforms.detect(rom)
    assert adapter.id == "n64"
    info = adapter.info(rom)
    assert info["internal_title"].startswith("CC DEMO")
