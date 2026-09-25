"""Shared test fixtures."""

from __future__ import annotations

import struct

import pytest

from controlled_corruptor.core import Region
from controlled_corruptor.core.prng import Rng


@pytest.fixture
def sample_data() -> bytes:
    """16 KiB of deterministic, varied bytes with some float32 values."""
    rng = Rng("test-sample")
    buf = bytearray(rng.randbytes(16384))
    # sprinkle some real float32s so float mutations have finite inputs
    for off in range(0x1000, 0x1400, 4):
        struct.pack_into(">f", buf, off, rng.uniform(-50.0, 50.0))
    return bytes(buf)


@pytest.fixture
def targets():
    return [Region("body", 0x100, 0x3F00, category="models", endianness="big")]


@pytest.fixture
def protected():
    return [
        Region("header", 0x0, 0x100, category="header", mutable=False),
        Region("footer", 0x3F00, 0x4000, category="header", mutable=False),
    ]
