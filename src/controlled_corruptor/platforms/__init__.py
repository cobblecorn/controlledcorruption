"""Platform adapter registry and detection.

New platforms register here. :func:`detect` returns the highest-confidence
adapter, always falling back to Generic.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .base import PlatformAdapter
from .generic import GenericPlatform
from .n64 import N64Platform

_REGISTRY: Dict[str, PlatformAdapter] = {}


def register(adapter: PlatformAdapter) -> None:
    _REGISTRY[adapter.id] = adapter


def get(platform_id: str) -> PlatformAdapter:
    try:
        return _REGISTRY[platform_id]
    except KeyError:
        raise KeyError(
            f"unknown platform {platform_id!r}; available: {', '.join(sorted(_REGISTRY))}"
        )


def available() -> List[str]:
    return sorted(_REGISTRY)


def detect(data: bytes) -> PlatformAdapter:
    """Return the best-matching adapter (Generic if nothing else matches).

    Only adapters that report a positive confidence are eligible, so a platform
    with a high base ``priority`` never wins on a file it does not recognize.
    Confidence dominates; ``priority`` only breaks ties between real matches.
    """
    best: Optional[PlatformAdapter] = None
    best_score = float("-inf")
    for adapter in _REGISTRY.values():
        confidence = adapter.detect(data)
        if confidence <= 0:
            continue
        score = confidence * 1000 + adapter.priority
        if score > best_score:
            best_score = score
            best = adapter
    return best or _REGISTRY["generic"]


for _a in (GenericPlatform(), N64Platform()):
    register(_a)


__all__ = ["PlatformAdapter", "register", "get", "available", "detect"]
