"""Helpers for authoring game profiles from the CLI/GUI.

Community reverse engineering should be able to expand support without touching
the application, so these build/extend profile JSON keyed by ROM hash. This is
the write side of :mod:`controlled_corruptor.profiles`.
"""

from __future__ import annotations

import json
import os
from typing import List, Optional, Sequence

from ..core.binary import BinaryFile
from ..core.regions import Region, parse_offset
from .schema import GameProfile


def parse_region_spec(spec: str) -> Region:
    """Parse ``name:category:start:end[:endian[:data_type]]``.

    Example: ``"Character Models:models:0x40000:0x80000:big:float32"``.
    """
    parts = spec.split(":")
    if len(parts) < 4:
        raise ValueError(
            f"region spec must be name:category:start:end[:endian[:dtype]], got {spec!r}")
    name, category, start, end = parts[0], parts[1], parts[2], parts[3]
    endian = parts[4] if len(parts) > 4 and parts[4] else "little"
    dtype = parts[5] if len(parts) > 5 and parts[5] else None
    return Region(name=name, category=category or "unknown",
                  start=parse_offset(start), end=parse_offset(end),
                  endianness=endian, data_type=dtype, source="user")


def new_profile(binary: BinaryFile, profile_id: str, name: str, *,
                platform: str = "generic",
                regions: Optional[Sequence[Region]] = None,
                notes: str = "") -> GameProfile:
    """Create a profile identifying ``binary`` by its SHA-256."""
    return GameProfile(
        id=profile_id, name=name, platform=platform,
        sha256=[binary.sha256], regions=list(regions or []),
        notes=notes or "User-authored profile.",
    )


def add_region(profile: GameProfile, region: Region) -> GameProfile:
    profile.regions.append(region)
    return profile


def add_hash(profile: GameProfile, sha256: str) -> GameProfile:
    """Register an additional ROM revision hash for this profile."""
    if sha256.lower() not in {h.lower() for h in profile.sha256}:
        profile.sha256.append(sha256)
    return profile


def save_profile(profile: GameProfile, path: str, *, overwrite: bool = True) -> str:
    if os.path.exists(path) and not overwrite:
        raise FileExistsError(f"refusing to overwrite {path}")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(profile.to_dict(), fh, indent=2)
    return path


def load_profile(path: str) -> GameProfile:
    with open(path, "r", encoding="utf-8") as fh:
        return GameProfile.from_dict(json.load(fh), source_path=path)


def regions_from_diff(a: bytes, b: bytes, *, merge_gap: int = 16,
                      category: str = "unknown") -> List[Region]:
    """Build regions from the ranges that differ between two dumps."""
    from ..core.diff import diff_regions

    return diff_regions(a, b, merge_gap=merge_gap, category=category)
