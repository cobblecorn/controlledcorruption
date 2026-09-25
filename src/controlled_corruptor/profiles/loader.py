"""Profile loading and lookup.

Profiles are plain JSON (YAML also supported when PyYAML is installed) found in
one or more search directories. Lookup is by source SHA-256.
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

from .schema import GameProfile

try:  # optional YAML support
    import yaml  # type: ignore

    _HAVE_YAML = True
except Exception:  # pragma: no cover
    _HAVE_YAML = False


def _default_profile_dirs() -> List[str]:
    dirs: List[str] = []
    env = os.environ.get("CCORRUPT_PROFILES")
    if env:
        dirs.extend(p for p in env.split(os.pathsep) if p)
    # Bundled profiles: <repo>/profiles
    here = os.path.dirname(os.path.abspath(__file__))
    repo_profiles = os.path.abspath(os.path.join(here, "..", "..", "..", "profiles"))
    dirs.append(repo_profiles)
    # User profiles
    dirs.append(os.path.expanduser("~/.config/ccorrupt/profiles"))
    return dirs


def load_profile_file(path: str) -> GameProfile:
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    if path.lower().endswith((".yaml", ".yml")):
        if not _HAVE_YAML:
            raise RuntimeError(f"PyYAML not installed; cannot read {path}")
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    return GameProfile.from_dict(data, source_path=path)


class ProfileLibrary:
    """Collection of profiles loaded from directories."""

    def __init__(self, dirs: Optional[List[str]] = None):
        self.dirs = dirs if dirs is not None else _default_profile_dirs()
        self._by_id: Dict[str, GameProfile] = {}
        self.errors: List[str] = []
        self.reload()

    def reload(self) -> None:
        self._by_id.clear()
        self.errors.clear()
        for d in self.dirs:
            if not os.path.isdir(d):
                continue
            for root, _dirs, files in os.walk(d):
                for fn in files:
                    if not fn.lower().endswith((".json", ".yaml", ".yml")):
                        continue
                    path = os.path.join(root, fn)
                    try:
                        profile = load_profile_file(path)
                        self._by_id[profile.id] = profile
                    except Exception as exc:  # pragma: no cover - defensive
                        self.errors.append(f"{path}: {exc}")

    def all(self) -> List[GameProfile]:
        return list(self._by_id.values())

    def get(self, profile_id: str) -> Optional[GameProfile]:
        return self._by_id.get(profile_id)

    def identify(self, sha256: str) -> Optional[GameProfile]:
        for p in self._by_id.values():
            if p.identify(sha256):
                return p
        return None
