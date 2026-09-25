"""Profile schema, loading and identification."""

from __future__ import annotations

import hashlib
import json

from controlled_corruptor.profiles import GameProfile, ProfileLibrary, load_profile_file
from controlled_corruptor.demo import build_demo_rom


def test_bundled_profiles_load_without_errors():
    lib = ProfileLibrary()
    assert lib.errors == []
    assert lib.get("cc-demo-n64") is not None


def test_demo_profile_identifies_demo_rom():
    lib = ProfileLibrary()
    sha = hashlib.sha256(build_demo_rom()).hexdigest()
    prof = lib.identify(sha)
    assert prof is not None
    assert prof.id == "cc-demo-n64"
    assert "models" in prof.categories()


def test_profile_from_dict_and_regions_for():
    prof = GameProfile.from_dict({
        "id": "t", "name": "T", "platform": "generic",
        "identification": {"sha256": ["deadbeef"]},
        "regions": [
            {"name": "m", "category": "models", "start": "0x10", "end": "0x20"},
            {"name": "a", "category": "audio", "start": "0x20", "end": "0x30"},
        ],
    })
    assert prof.identify("DEADBEEF")  # case-insensitive
    got = prof.regions_for(["models"])
    assert [r.name for r in got] == ["m"]


def test_profile_file_roundtrip(tmp_path):
    prof = GameProfile.from_dict({
        "id": "rt", "name": "RT", "platform": "n64",
        "identification": {"sha256": ["abc"]},
        "regions": [{"name": "x", "category": "maps", "start": 0, "end": 16}],
    })
    path = tmp_path / "rt.json"
    path.write_text(json.dumps(prof.to_dict()))
    loaded = load_profile_file(str(path))
    assert loaded.id == "rt"
    assert loaded.categories() == ["maps"]
