"""Deterministic, versioned pseudo random number generator.

Reproducibility is a hard requirement of this project: the *same* source
file, settings and seed must always yield the *same* corrupted output. We
therefore do **not** rely on Python's ``random`` module (whose stream is an
implementation detail). Instead we implement a small, fully specified PRNG so
the algorithm can, if desired, be re-implemented byte-for-byte in another
language later.

Algorithm
---------
* String/int seeds are folded to a 64-bit state with SHA-256 (first 8 bytes,
  little-endian) so arbitrary seeds like ``"CODY-3491281"`` work.
* That state is expanded with **SplitMix64** into the four 64-bit words of
  the generator.
* Numbers are produced with **xoshiro256\\*\\*** (Blackman & Vigna).

The version string is stored with every project so a future change to the
algorithm can be detected and older corruptions still reproduced.
"""

from __future__ import annotations

import hashlib
import struct
from typing import Sequence, TypeVar

_MASK64 = (1 << 64) - 1

#: Bump this whenever the number stream changes in a backwards-incompatible
#: way. Projects/seeds record the version they were generated with.
PRNG_VERSION = "ccprng-1"

T = TypeVar("T")


def seed_to_u64(seed: object) -> int:
    """Fold an arbitrary seed (str or int) into a 64-bit integer.

    Integers are used directly (masked to 64 bits). Everything else is
    stringified and hashed with SHA-256, taking the first 8 bytes little
    endian. This keeps string seeds stable across platforms and versions.
    """
    if isinstance(seed, bool):  # bool is an int subclass; be explicit
        seed = int(seed)
    if isinstance(seed, int):
        return seed & _MASK64
    digest = hashlib.sha256(str(seed).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "little")


class SplitMix64:
    """SplitMix64 -- used only to seed the main generator."""

    __slots__ = ("state",)

    def __init__(self, state: int) -> None:
        self.state = state & _MASK64

    def next(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & _MASK64
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _MASK64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _MASK64
        z ^= z >> 31
        return z & _MASK64


def _rotl(x: int, k: int) -> int:
    return ((x << k) | (x >> (64 - k))) & _MASK64


class Rng:
    """xoshiro256** deterministic generator with convenience helpers."""

    version = PRNG_VERSION

    __slots__ = ("s",)

    def __init__(self, seed: object) -> None:
        sm = SplitMix64(seed_to_u64(seed))
        self.s = [sm.next() for _ in range(4)]

    # -- core ---------------------------------------------------------------
    def next_u64(self) -> int:
        s = self.s
        result = (_rotl((s[1] * 5) & _MASK64, 7) * 9) & _MASK64
        t = (s[1] << 17) & _MASK64
        s[2] ^= s[0]
        s[3] ^= s[1]
        s[1] ^= s[2]
        s[0] ^= s[3]
        s[2] ^= t
        s[3] = _rotl(s[3], 45)
        return result

    # -- helpers ------------------------------------------------------------
    def random(self) -> float:
        """Float in [0.0, 1.0) with 53 bits of resolution."""
        return (self.next_u64() >> 11) * (1.0 / (1 << 53))

    def randbelow(self, n: int) -> int:
        """Uniform integer in [0, n) via rejection sampling (no modulo bias)."""
        if n <= 0:
            raise ValueError("n must be positive")
        if n & (n - 1) == 0:  # power of two -> mask
            return self.next_u64() & (n - 1)
        # Largest multiple of n that fits in 64 bits; reject above it.
        limit = _MASK64 - (_MASK64 % n)
        while True:
            r = self.next_u64()
            if r <= limit:
                return r % n

    def randint(self, a: int, b: int) -> int:
        """Uniform integer in the inclusive range [a, b]."""
        if b < a:
            raise ValueError("empty range for randint")
        return a + self.randbelow(b - a + 1)

    def uniform(self, a: float, b: float) -> float:
        """Float in [a, b)."""
        return a + (b - a) * self.random()

    def choice(self, seq: Sequence[T]) -> T:
        if not seq:
            raise IndexError("cannot choose from an empty sequence")
        return seq[self.randbelow(len(seq))]

    def weighted_choice(self, items: Sequence[T], weights: Sequence[float]) -> T:
        """Pick an item with probability proportional to its weight."""
        total = float(sum(weights))
        if total <= 0:
            raise ValueError("weights must sum to a positive value")
        r = self.random() * total
        upto = 0.0
        for item, w in zip(items, weights):
            upto += w
            if r < upto:
                return item
        return items[-1]  # floating point guard

    def sample_bits(self, count: int, width: int = 8) -> int:
        """Return a bitmask with ``count`` distinct bits set within ``width``."""
        count = max(0, min(count, width))
        chosen = 0
        picked = 0
        positions = list(range(width))
        # Partial Fisher-Yates so the draw sequence is deterministic.
        for i in range(count):
            j = i + self.randbelow(width - i)
            positions[i], positions[j] = positions[j], positions[i]
            chosen |= 1 << positions[i]
            picked += 1
        return chosen

    def randbytes(self, n: int) -> bytes:
        out = bytearray()
        while len(out) < n:
            out += struct.pack("<Q", self.next_u64())
        return bytes(out[:n])
