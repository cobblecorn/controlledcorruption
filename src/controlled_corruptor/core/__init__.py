"""Core, game-agnostic corruption engine and supporting types."""

from __future__ import annotations

from .binary import BinaryFile, compute_hashes, from_bytes, load_binary, write_output
from .engine import Engine, EngineResult
from .history import MutationLog, MutationRecord
from .prng import PRNG_VERSION, Rng
from .regions import CATEGORIES, Region, parse_offset
from .settings import ALL_TYPES, DEFAULT_TYPES, MutationSettings
from .validation import Check, Level, ValidationReport

__all__ = [
    "BinaryFile",
    "compute_hashes",
    "from_bytes",
    "load_binary",
    "write_output",
    "Engine",
    "EngineResult",
    "MutationLog",
    "MutationRecord",
    "PRNG_VERSION",
    "Rng",
    "CATEGORIES",
    "Region",
    "parse_offset",
    "ALL_TYPES",
    "DEFAULT_TYPES",
    "MutationSettings",
    "Check",
    "Level",
    "ValidationReport",
]
