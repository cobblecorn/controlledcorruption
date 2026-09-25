"""High-level orchestration shared by the CLI and the GUI.

The engine is pure; this module assembles the inputs for it: pick a platform
adapter, optionally apply a game profile, gather target + protected regions,
run the engine, then let the platform repair checksums. Both front-ends call
:func:`corrupt` so they always behave identically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from .. import platforms
from ..platforms.base import PlatformAdapter
from ..profiles import GameProfile, ProfileLibrary
from .binary import BinaryFile
from .engine import Engine, EngineResult
from .regions import Interval, Region
from .settings import MutationSettings

Interval_ = Tuple[int, int]


@dataclass
class CorruptionResult:
    output: bytes
    engine_result: EngineResult
    platform: PlatformAdapter
    profile: Optional[GameProfile]
    protected: List[Region] = field(default_factory=list)
    targets: List[Region] = field(default_factory=list)
    checksum_repaired: bool = False


def resolve_profile(
    binary: BinaryFile,
    *,
    profile: Optional[GameProfile] = None,
    profile_id: Optional[str] = None,
    library: Optional[ProfileLibrary] = None,
    auto_identify: bool = True,
) -> Optional[GameProfile]:
    """Pick a profile explicitly, by id, or by matching the source hash."""
    if profile is not None:
        return profile
    lib = library or ProfileLibrary()
    if profile_id:
        p = lib.get(profile_id)
        if p is None:
            raise KeyError(f"profile {profile_id!r} not found")
        return p
    if auto_identify:
        return lib.identify(binary.sha256)
    return None


def gather_regions(
    binary: BinaryFile,
    platform: PlatformAdapter,
    profile: Optional[GameProfile],
    *,
    extra_protected: Optional[Sequence[Region]] = None,
) -> Tuple[List[Region], List[Region]]:
    """Return (targets, protected) after combining platform + profile + user."""
    targets: List[Region] = []
    protected: List[Region] = list(platform.protected_regions(binary.data))

    if profile is not None:
        targets.extend(profile.regions)
        if profile.inherit_platform_protected is False:
            protected = []
        protected.extend(profile.protected)

    if extra_protected:
        protected.extend(extra_protected)
    return targets, protected


def corrupt(
    binary: BinaryFile,
    settings: MutationSettings,
    *,
    categories: Optional[Sequence[str]] = None,
    profile: Optional[GameProfile] = None,
    profile_id: Optional[str] = None,
    library: Optional[ProfileLibrary] = None,
    auto_identify: bool = True,
    platform: Optional[PlatformAdapter] = None,
    target_intervals: Optional[Sequence[Interval]] = None,
    extra_protected: Optional[Sequence[Region]] = None,
    repair_checksum: bool = True,
) -> CorruptionResult:
    """Run the full corruption pipeline and return the result."""
    plat = platform or platforms.detect(binary.data)
    prof = resolve_profile(
        binary, profile=profile, profile_id=profile_id,
        library=library, auto_identify=auto_identify,
    )
    if prof is not None and prof.platform and platform is None:
        # Prefer the profile's declared platform adapter if we have it.
        try:
            plat = platforms.get(prof.platform)
        except KeyError:
            pass

    targets, protected = gather_regions(
        binary, plat, prof, extra_protected=extra_protected
    )

    engine = Engine(settings)
    result = engine.run(
        binary.data,
        targets=targets,
        protected=protected,
        target_intervals=target_intervals,
        categories=categories,
    )

    output = result.data
    repaired = False
    if repair_checksum:
        fixed = plat.repair_checksum(output)
        if fixed != output:
            repaired = True
        output = fixed

    return CorruptionResult(
        output=output,
        engine_result=result,
        platform=plat,
        profile=prof,
        protected=protected,
        targets=targets,
        checksum_repaired=repaired,
    )
