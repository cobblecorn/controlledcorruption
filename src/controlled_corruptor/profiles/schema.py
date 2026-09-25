"""Game profile model and schema.

A profile is *external* game knowledge (JSON/YAML), identified by ROM hash
rather than filename so different dumps of the same game match, and different
revisions are handled separately. Profiles carry the known regions and may add
their own protected regions on top of the platform's.

The mutation engine never imports this; profiles feed it regions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from ..core.regions import Region


@dataclass
class GameProfile:
    id: str
    name: str
    platform: str = "generic"
    sha256: List[str] = field(default_factory=list)   # accepted source hashes
    regions: List[Region] = field(default_factory=list)
    protected: List[Region] = field(default_factory=list)
    inherit_platform_protected: bool = True
    notes: str = ""
    source_path: Optional[str] = None  # where the profile was loaded from

    # -- identification -----------------------------------------------------
    def identify(self, sha256: str) -> bool:
        """Profiles preferably identify games by hash, not filename."""
        return sha256.lower() in {h.lower() for h in self.sha256}

    def categories(self) -> List[str]:
        seen = []
        for r in self.regions:
            if r.category not in seen:
                seen.append(r.category)
        return seen

    def regions_for(self, categories: Optional[List[str]]) -> List[Region]:
        return [r for r in self.regions if r.mutable and r.matches(categories)]

    # -- (de)serialization --------------------------------------------------
    @classmethod
    def from_dict(cls, d: dict, source_path: Optional[str] = None) -> "GameProfile":
        ident = d.get("identification", {})
        sha = ident.get("sha256", d.get("sha256", []))
        if isinstance(sha, str):
            sha = [sha]
        regions = [_region_from(r, source=d.get("id", "profile"))
                   for r in d.get("regions", [])]
        protected = [_region_from(r, source=d.get("id", "profile"), mutable=False)
                     for r in d.get("protected", [])]
        return cls(
            id=d.get("id") or d.get("name", "profile"),
            name=d.get("name", d.get("id", "Unnamed")),
            platform=d.get("platform", "generic"),
            sha256=list(sha),
            regions=regions,
            protected=protected,
            inherit_platform_protected=d.get("inherit_platform_protected", True),
            notes=d.get("notes", ""),
            source_path=source_path,
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "platform": self.platform,
            "identification": {"sha256": list(self.sha256)},
            "inherit_platform_protected": self.inherit_platform_protected,
            "regions": [r.to_dict() for r in self.regions],
            "protected": [r.to_dict() for r in self.protected],
            "notes": self.notes,
        }


def _region_from(d: dict, source: str = "", mutable: Optional[bool] = None) -> Region:
    region = Region.from_dict({**d, "source": d.get("source", f"profile:{source}")})
    if mutable is not None:
        region.mutable = mutable
    return region
