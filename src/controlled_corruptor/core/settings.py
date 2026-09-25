"""Mutation settings.

Per the handoff, "intensity" is deliberately split into two orthogonal knobs:

* **density**   -- *how many* things get mutated (fraction of mutable bytes).
* **magnitude** -- *how hard* each mutation hits (0..1, strategy-dependent).

A simplified UI slider can drive both, but internally they stay separate so
you can express "few huge changes" vs "many tiny changes".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .prng import PRNG_VERSION

#: Mutation strategies enabled when the caller does not specify a set.
DEFAULT_TYPES: List[str] = [
    "byte_replace",
    "bit_flip",
    "byte_offset",
    "int16",
    "int32",
    "float32",
]

ALL_TYPES: List[str] = [
    "byte_replace",
    "bit_flip",
    "byte_offset",
    "int16",
    "int32",
    "float32",
    "block_swap",
    "block_repeat",
    "block_shift",
]


@dataclass
class MutationSettings:
    """Everything needed to drive the engine except the data + regions.

    ``seed`` and ``prng_version`` live here so a settings object fully and
    reproducibly determines an output for a given input + regions.
    """

    seed: object = 0
    density: float = 0.002          # fraction of mutable bytes to touch
    magnitude: float = 0.35         # 0..1 strength of each mutation
    types: List[str] = field(default_factory=lambda: list(DEFAULT_TYPES))
    type_weights: Dict[str, float] = field(default_factory=dict)

    # byte/int overflow behavior
    wrap: bool = True               # True: wrap on overflow, False: clamp

    # integer interpretation defaults (regions may override)
    endianness: str = "little"
    signed: bool = True

    # float safety
    allow_nan: bool = False

    # block-operation window
    block_size: int = 16

    prng_version: str = PRNG_VERSION

    def weight_for(self, name: str) -> float:
        return float(self.type_weights.get(name, 1.0))

    def to_dict(self) -> dict:
        return {
            "seed": self.seed,
            "density": self.density,
            "magnitude": self.magnitude,
            "types": list(self.types),
            "type_weights": dict(self.type_weights),
            "wrap": self.wrap,
            "endianness": self.endianness,
            "signed": self.signed,
            "allow_nan": self.allow_nan,
            "block_size": self.block_size,
            "prng_version": self.prng_version,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MutationSettings":
        return cls(
            seed=d.get("seed", 0),
            density=d.get("density", 0.002),
            magnitude=d.get("magnitude", 0.35),
            types=list(d.get("types", DEFAULT_TYPES)),
            type_weights=dict(d.get("type_weights", {})),
            wrap=d.get("wrap", True),
            endianness=d.get("endianness", "little"),
            signed=d.get("signed", True),
            allow_nan=d.get("allow_nan", False),
            block_size=d.get("block_size", 16),
            prng_version=d.get("prng_version", PRNG_VERSION),
        )

    @staticmethod
    def from_intensity(intensity: float, **overrides) -> "MutationSettings":
        """Map a single 0..1 UI slider onto sensible density/magnitude.

        Kept intentionally simple; the two values remain independent afterward.
        """
        intensity = max(0.0, min(1.0, intensity))
        density = 0.0005 + intensity * 0.05      # ~0.05% .. ~5%
        magnitude = 0.1 + intensity * 0.8        # 10% .. 90%
        return MutationSettings(density=density, magnitude=magnitude, **overrides)
