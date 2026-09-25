"""Hex viewer and value interpretation.

A small, dependency-free hex dump plus "interpret these bytes as ..." helper,
so the tool doubles as a lightweight reverse-engineering utility. The GUI hex
panel and the CLI ``hex`` command both call these.
"""

from __future__ import annotations

import struct
from typing import Dict, List, Optional, Tuple

_PRINTABLE = bytes(range(0x20, 0x7F))


def _ascii(byte: int) -> str:
    return chr(byte) if byte in _PRINTABLE else "."


def hex_dump(
    data: bytes,
    start: int = 0,
    length: Optional[int] = None,
    *,
    width: int = 16,
    base_offset: int = 0,
) -> str:
    """Classic ``offset  hex bytes  |ascii|`` dump.

    ``start`` is the index into ``data``; ``base_offset`` is added to the
    printed address (useful when dumping a slice of a larger file).
    """
    if length is None:
        length = len(data) - start
    end = min(len(data), start + max(0, length))
    lines: List[str] = []
    for row in range(start, end, width):
        chunk = data[row:min(row + width, end)]
        hex_parts = []
        for i in range(width):
            if i < len(chunk):
                hex_parts.append(f"{chunk[i]:02X}")
            else:
                hex_parts.append("  ")
            if i == width // 2 - 1:
                hex_parts.append("")  # gutter between halves
        hex_str = " ".join(hex_parts)
        ascii_str = "".join(_ascii(b) for b in chunk)
        lines.append(f"{base_offset + row:08X}  {hex_str}  |{ascii_str}|")
    return "\n".join(lines)


def interpret(data: bytes, offset: int, *, endian: str = "little") -> Dict[str, object]:
    """Interpret the bytes at ``offset`` as a range of common types.

    Missing types (not enough bytes left) are simply omitted.
    """
    e = "<" if endian == "little" else ">"
    out: Dict[str, object] = {"offset": offset, "endian": endian}
    n = len(data)

    def take(fmt: str, size: int):
        if offset + size > n:
            return None
        return struct.unpack_from(e + fmt, data, offset)[0]

    mapping: List[Tuple[str, str, int]] = [
        ("int8", "b", 1), ("uint8", "B", 1),
        ("int16", "h", 2), ("uint16", "H", 2),
        ("int32", "i", 4), ("uint32", "I", 4),
        ("int64", "q", 8), ("uint64", "Q", 8),
        ("float32", "f", 4), ("float64", "d", 8),
    ]
    for name, fmt, size in mapping:
        val = take(fmt, size)
        if val is not None:
            out[name] = val

    # Pointer view: a uint32 rendered as a hex address.
    ptr = take("I", 4)
    if ptr is not None:
        out["pointer"] = f"0x{ptr:08X}"

    # Short ASCII preview.
    ascii_bytes = data[offset:offset + 16]
    out["ascii"] = "".join(_ascii(b) for b in ascii_bytes)
    return out


def format_interpret(data: bytes, offset: int, *, endian: str = "little") -> str:
    info = interpret(data, offset, endian=endian)
    lines = [f"offset 0x{offset:08X} ({endian}-endian)"]
    order = ["int8", "uint8", "int16", "uint16", "int32", "uint32",
             "int64", "uint64", "float32", "float64", "pointer", "ascii"]
    for key in order:
        if key in info:
            val = info[key]
            if key in ("float32", "float64"):
                val = f"{val:.6g}"
            lines.append(f"  {key:8s}: {val}")
    return "\n".join(lines)
