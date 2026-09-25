"""Generate a small, synthetic, deterministic demo ROM.

This is NOT a real game -- it is fabricated filler used so the whole pipeline
(profile identification, region targeting, checksum repair, project save/load)
can be demonstrated and tested without any copyrighted ROM. The bytes are
produced from a fixed seed so the file (and therefore its SHA-256) is stable.

The layout intentionally mimics an N64 ROM so the N64 adapter recognizes it:

    0x00000000  header (magic, title)
    0x00000040  boot code (filler)
    0x00001000  "code"      (protected-ish demo region)
    0x00040000  "models"    (float32 vertex-like triplets)
    0x00080000  "animations"(float32 values)
    0x000C0000  "textures"  (byte data)
    0x00101000  end of checksum window ...
"""

from __future__ import annotations

import struct

from .core.prng import Rng

DEMO_SIZE = 0x1000 + 0x100000 + 0x40000  # past the N64 checksum window

# Region map used by the bundled demo profile (keep in sync with the profile).
DEMO_REGIONS = {
    "code": (0x00001000, 0x00040000),
    "models": (0x00040000, 0x00080000),
    "animations": (0x00080000, 0x000C0000),
    "textures": (0x000C0000, 0x00101000),
}


def build_demo_rom() -> bytes:
    rng = Rng("controlled-corruptor-demo-v1")
    buf = bytearray(DEMO_SIZE)

    # Header: N64 big-endian magic + internal title.
    buf[0:4] = b"\x80\x37\x12\x40"
    title = b"CC DEMO ROM"
    buf[0x20:0x20 + len(title)] = title

    # Boot code + everything: deterministic filler.
    for i in range(0x40, DEMO_SIZE, 8):
        chunk = struct.pack("<Q", rng.next_u64())
        buf[i:i + 8] = chunk[: min(8, DEMO_SIZE - i)]

    # Lay down float32 vertex-like triplets in the "models" region so semantic
    # float mutations have realistic-looking data to chew on.
    ms, me = DEMO_REGIONS["models"]
    for off in range(ms, me, 12):
        if off + 12 > me:
            break
        for k in range(3):
            struct.pack_into(">f", buf, off + k * 4, rng.uniform(-100.0, 100.0))

    return bytes(buf)


if __name__ == "__main__":  # pragma: no cover
    import hashlib
    import sys

    data = build_demo_rom()
    out = sys.argv[1] if len(sys.argv) > 1 else "demo.z64"
    with open(out, "wb") as fh:
        fh.write(data)
    print(out, len(data), "bytes")
    print("sha256:", hashlib.sha256(data).hexdigest())
