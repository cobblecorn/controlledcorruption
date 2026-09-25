"""Batch mutation generation.

Produce many corrupted variants of one source across a series of seeds, sharing
all other settings. Useful for generating a set of corruptions to browse, or
seeding the guided-fuzz sweep.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Union

from ..profiles import GameProfile, ProfileLibrary
from .binary import BinaryFile
from .pipeline import corrupt
from .regions import Interval
from .settings import MutationSettings

SeedLike = Union[str, int]


@dataclass
class BatchItem:
    seed: SeedLike
    output: bytes
    summary: dict


def seed_series(count: int, *, prefix: str = "", start: int = 0) -> List[SeedLike]:
    """Build ``count`` seeds. With a prefix -> strings, else integers."""
    if prefix:
        return [f"{prefix}{start + i}" for i in range(count)]
    return [start + i for i in range(count)]


def generate_batch(
    binary: BinaryFile,
    base_settings: MutationSettings,
    seeds: Sequence[SeedLike],
    *,
    categories: Optional[Sequence[str]] = None,
    profile: Optional[GameProfile] = None,
    profile_id: Optional[str] = None,
    library: Optional[ProfileLibrary] = None,
    auto_identify: bool = True,
    target_intervals: Optional[Sequence[Interval]] = None,
    repair_checksum: bool = True,
) -> List[BatchItem]:
    """Generate one corrupted output per seed (all other settings shared)."""
    lib = library or ProfileLibrary()
    items: List[BatchItem] = []
    base = base_settings.to_dict()
    for seed in seeds:
        settings = MutationSettings.from_dict({**base, "seed": seed})
        result = corrupt(
            binary, settings,
            categories=categories, profile=profile, profile_id=profile_id,
            library=lib, auto_identify=auto_identify,
            target_intervals=target_intervals, repair_checksum=repair_checksum,
        )
        items.append(BatchItem(seed=seed, output=result.output,
                               summary=result.engine_result.log.summary()))
    return items
