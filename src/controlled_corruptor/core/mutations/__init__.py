"""Mutation strategy registry.

New strategies register themselves here so both the engine and the UI can
discover them by name. Keeping this as a plain dict makes it trivial for a
plugin to add a strategy at import time.
"""

from __future__ import annotations

from typing import Dict, List

from .base import Mutation, MutationContext
from .block_ops import BlockRepeat, BlockShift, BlockSwap
from .byte_ops import BitFlip, ByteOffset, ByteReplace
from .float_ops import Float32Mutation
from .integer_ops import Int16Mutation, Int32Mutation

_REGISTRY: Dict[str, Mutation] = {}


def register(mutation: Mutation) -> None:
    _REGISTRY[mutation.name] = mutation


def get(name: str) -> Mutation:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(
            f"unknown mutation type {name!r}; available: {', '.join(sorted(_REGISTRY))}"
        )


def available() -> List[str]:
    return sorted(_REGISTRY)


for _m in (
    ByteReplace(),
    BitFlip(),
    ByteOffset(),
    Int16Mutation(),
    Int32Mutation(),
    Float32Mutation(),
    BlockSwap(),
    BlockRepeat(),
    BlockShift(),
):
    register(_m)


__all__ = ["Mutation", "MutationContext", "register", "get", "available"]
