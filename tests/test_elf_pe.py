"""ELF and PE adapter parsing, detection and header protection."""

from __future__ import annotations

import struct

from controlled_corruptor import platforms
from controlled_corruptor.platforms.elf import ELFPlatform
from controlled_corruptor.platforms.pe import PEPlatform


def _elf32(endian="little") -> bytes:
    e = "<" if endian == "little" else ">"
    ei_data = 1 if endian == "little" else 2
    buf = bytearray(0x200)
    buf[0:4] = b"\x7fELF"
    buf[4] = 1          # 32-bit
    buf[5] = ei_data
    buf[6] = 1          # version
    phoff, shoff = 0x34, 0x100
    struct.pack_into(e + "I", buf, 0x1C, phoff)
    struct.pack_into(e + "I", buf, 0x20, shoff)
    # ehsize, phentsize, phnum, shentsize, shnum
    struct.pack_into(e + "HHHHH", buf, 0x28, 0x34, 0x20, 2, 0x28, 3)
    return bytes(buf)


def _pe() -> bytes:
    buf = bytearray(0x400)
    buf[0:2] = b"MZ"
    lfanew = 0x80
    struct.pack_into("<I", buf, 0x3C, lfanew)
    buf[lfanew:lfanew + 4] = b"PE\x00\x00"
    struct.pack_into("<H", buf, lfanew + 6, 3)    # num sections
    struct.pack_into("<H", buf, lfanew + 20, 0xE0)  # optional header size
    return bytes(buf)


def test_elf_detect_and_endianness():
    little = _elf32("little")
    big = _elf32("big")
    assert platforms.detect(little).id == "elf"
    assert ELFPlatform().endianness(little) == "little"
    assert ELFPlatform().endianness(big) == "big"


def test_elf_protects_header_and_tables():
    data = _elf32("little")
    prot = ELFPlatform().protected_regions(data)
    names = {r.name for r in prot}
    assert "ELF Header" in names
    assert "ELF Program Headers" in names
    assert "ELF Section Headers" in names
    # program headers at 0x34, 2 * 0x20 = 0x40 bytes
    ph = next(r for r in prot if r.name == "ELF Program Headers")
    assert ph.start == 0x34 and ph.end == 0x34 + 2 * 0x20


def test_elf_rejects_garbage():
    assert ELFPlatform().detect(b"\x7fELF" + b"\xff" * 60) == 0.0


def test_pe_detect_and_protect():
    data = _pe()
    assert platforms.detect(data).id == "pe"
    prot = PEPlatform().protected_regions(data)
    assert prot and prot[0].start == 0
    # headers_end = lfanew + 24 + opt_size + num_sections*40
    assert prot[0].end == 0x80 + 24 + 0xE0 + 3 * 40


def test_pe_rejects_mz_without_pe():
    buf = bytearray(0x100)
    buf[0:2] = b"MZ"
    struct.pack_into("<I", buf, 0x3C, 0x80)  # points at zeros, no "PE\0\0"
    assert PEPlatform().detect(bytes(buf)) == 0.0


def test_both_registered():
    assert {"elf", "pe"} <= set(platforms.available())
