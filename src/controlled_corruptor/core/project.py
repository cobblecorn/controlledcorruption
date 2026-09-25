"""Corruption project and shareable seed formats.

Two on-disk formats, both JSON:

* ``.ccproject`` -- a full project: source identity, platform/profile, and a
  **mutation stack** of layers. The stack is non-destructive: output is always
  rebuilt as ``original + enabled layers``, so toggling a layer off simply
  regenerates without it (no cumulative accidental corruption).

* ``.ccseed``    -- a compact, shareable recipe (source hash, profile id, seed,
  settings). It lets people reproduce a corruption **without** sharing the ROM.

Neither format ever stores copyrighted ROM contents -- only hashes and offsets.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from .. import platforms
from ..platforms.base import PlatformAdapter
from ..profiles import GameProfile, ProfileLibrary
from .binary import BinaryFile
from .engine import Engine, EngineResult
from .history import MutationLog
from .pipeline import gather_regions
from .prng import PRNG_VERSION
from .regions import Interval, Region
from .settings import MutationSettings

PROJECT_VERSION = 1
SEED_VERSION = 1


# --------------------------------------------------------------------------
# Mutation stack layer
# --------------------------------------------------------------------------
@dataclass
class Layer:
    """One entry in the non-destructive mutation stack."""

    name: str
    settings: MutationSettings
    enabled: bool = True
    categories: Optional[List[str]] = None
    target_intervals: Optional[List[Interval]] = None
    extra_protected: List[Region] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "categories": self.categories,
            "target_intervals": (
                [[s, e] for s, e in self.target_intervals]
                if self.target_intervals is not None else None
            ),
            "extra_protected": [r.to_dict() for r in self.extra_protected],
            "settings": self.settings.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Layer":
        ti = d.get("target_intervals")
        return cls(
            name=d.get("name", "layer"),
            settings=MutationSettings.from_dict(d.get("settings", {})),
            enabled=d.get("enabled", True),
            categories=d.get("categories"),
            target_intervals=[(int(s), int(e)) for s, e in ti] if ti else None,
            extra_protected=[Region.from_dict(r) for r in d.get("extra_protected", [])],
        )


@dataclass
class ApplyResult:
    output: bytes
    layer_results: List[Tuple[Layer, EngineResult]]
    platform: PlatformAdapter
    profile: Optional[GameProfile]
    checksum_repaired: bool = False

    @property
    def combined_log(self) -> MutationLog:
        log = MutationLog()
        for _layer, res in self.layer_results:
            log.records.extend(res.log.records)
        return log


# --------------------------------------------------------------------------
# Project
# --------------------------------------------------------------------------
@dataclass
class CorruptionProject:
    source_sha256: str
    source_filename: Optional[str] = None
    source_size: Optional[int] = None
    platform: Optional[str] = None
    profile_id: Optional[str] = None
    repair_checksum: bool = True
    layers: List[Layer] = field(default_factory=list)
    notes: str = ""
    version: int = PROJECT_VERSION

    # -- convenience constructors ------------------------------------------
    @classmethod
    def single(
        cls,
        binary: BinaryFile,
        settings: MutationSettings,
        *,
        categories: Optional[List[str]] = None,
        profile_id: Optional[str] = None,
        platform: Optional[str] = None,
        target_intervals: Optional[Sequence[Interval]] = None,
        repair_checksum: bool = True,
        layer_name: str = "Layer 1",
        notes: str = "",
    ) -> "CorruptionProject":
        layer = Layer(
            name=layer_name,
            settings=settings,
            categories=list(categories) if categories else None,
            target_intervals=list(target_intervals) if target_intervals else None,
        )
        return cls(
            source_sha256=binary.sha256,
            source_filename=binary.filename,
            source_size=binary.size,
            platform=platform,
            profile_id=profile_id,
            repair_checksum=repair_checksum,
            layers=[layer],
            notes=notes,
        )

    # -- source verification ------------------------------------------------
    def verify_source(self, binary: BinaryFile) -> Tuple[bool, str]:
        if binary.sha256.lower() == self.source_sha256.lower():
            return True, "source hash matches project"
        return False, (
            f"source hash mismatch: project expects {self.source_sha256} "
            f"but file is {binary.sha256}"
        )

    # -- apply (non-destructive stack) -------------------------------------
    def apply(
        self,
        binary: BinaryFile,
        *,
        library: Optional[ProfileLibrary] = None,
        platform: Optional[PlatformAdapter] = None,
        verify: bool = True,
    ) -> ApplyResult:
        if verify:
            ok, msg = self.verify_source(binary)
            if not ok:
                raise ValueError(msg)

        plat = platform
        if plat is None:
            if self.platform:
                try:
                    plat = platforms.get(self.platform)
                except KeyError:
                    plat = platforms.detect(binary.data)
            else:
                plat = platforms.detect(binary.data)

        prof: Optional[GameProfile] = None
        if self.profile_id:
            lib = library or ProfileLibrary()
            prof = lib.get(self.profile_id)

        working = binary.data
        layer_results: List[Tuple[Layer, EngineResult]] = []
        for layer in self.layers:
            if not layer.enabled:
                continue
            # Regions are offset-based and size-stable, so gather from the
            # original binary; run the engine on the running buffer.
            targets, protected = gather_regions(
                binary, plat, prof, extra_protected=layer.extra_protected
            )
            engine = Engine(layer.settings)
            res = engine.run(
                working,
                targets=targets,
                protected=protected,
                target_intervals=layer.target_intervals,
                categories=layer.categories,
            )
            working = res.data
            layer_results.append((layer, res))

        repaired = False
        if self.repair_checksum:
            fixed = plat.repair_checksum(working)
            repaired = fixed != working
            working = fixed

        return ApplyResult(
            output=working,
            layer_results=layer_results,
            platform=plat,
            profile=prof,
            checksum_repaired=repaired,
        )

    # -- (de)serialization --------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "kind": "ccproject",
            "source": {
                "sha256": self.source_sha256,
                "filename": self.source_filename,
                "size": self.source_size,
            },
            "platform": self.platform,
            "profile": self.profile_id,
            "repair_checksum": self.repair_checksum,
            "notes": self.notes,
            "prng_version": PRNG_VERSION,
            "layers": [l.to_dict() for l in self.layers],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CorruptionProject":
        src = d.get("source", {})
        return cls(
            source_sha256=src.get("sha256", ""),
            source_filename=src.get("filename"),
            source_size=src.get("size"),
            platform=d.get("platform"),
            profile_id=d.get("profile"),
            repair_checksum=d.get("repair_checksum", True),
            layers=[Layer.from_dict(l) for l in d.get("layers", [])],
            notes=d.get("notes", ""),
            version=d.get("version", PROJECT_VERSION),
        )

    def save(self, path: str) -> str:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2)
        return path

    @classmethod
    def load(cls, path: str) -> "CorruptionProject":
        with open(path, "r", encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))


# --------------------------------------------------------------------------
# Shareable seed / recipe
# --------------------------------------------------------------------------
@dataclass
class CorruptionSeed:
    source_sha256: str
    settings: MutationSettings
    profile_id: Optional[str] = None
    platform: Optional[str] = None
    categories: Optional[List[str]] = None
    repair_checksum: bool = True
    notes: str = ""
    version: int = SEED_VERSION

    @classmethod
    def from_project(cls, project: CorruptionProject) -> "CorruptionSeed":
        if len(project.layers) != 1:
            raise ValueError(".ccseed export requires exactly one layer")
        layer = project.layers[0]
        return cls(
            source_sha256=project.source_sha256,
            settings=layer.settings,
            profile_id=project.profile_id,
            platform=project.platform,
            categories=layer.categories,
            repair_checksum=project.repair_checksum,
            notes=project.notes,
        )

    def to_project(self) -> CorruptionProject:
        return CorruptionProject(
            source_sha256=self.source_sha256,
            platform=self.platform,
            profile_id=self.profile_id,
            repair_checksum=self.repair_checksum,
            layers=[Layer(name="Layer 1", settings=self.settings,
                          categories=self.categories)],
            notes=self.notes,
        )

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "kind": "ccseed",
            "source_sha256": self.source_sha256,
            "platform": self.platform,
            "profile": self.profile_id,
            "categories": self.categories,
            "repair_checksum": self.repair_checksum,
            "notes": self.notes,
            "prng_version": PRNG_VERSION,
            "settings": self.settings.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CorruptionSeed":
        return cls(
            source_sha256=d.get("source_sha256", ""),
            settings=MutationSettings.from_dict(d.get("settings", {})),
            profile_id=d.get("profile"),
            platform=d.get("platform"),
            categories=d.get("categories"),
            repair_checksum=d.get("repair_checksum", True),
            notes=d.get("notes", ""),
            version=d.get("version", SEED_VERSION),
        )

    def save(self, path: str) -> str:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2)
        return path

    @classmethod
    def load(cls, path: str) -> "CorruptionSeed":
        with open(path, "r", encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))
