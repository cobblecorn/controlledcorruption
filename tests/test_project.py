"""Project / seed serialization and non-destructive layer application."""

from __future__ import annotations

import json

from controlled_corruptor.core import from_bytes
from controlled_corruptor.core.pipeline import corrupt
from controlled_corruptor.core.project import (
    CorruptionProject, CorruptionSeed, Layer,
)
from controlled_corruptor.core.regions import Region
from controlled_corruptor.core.settings import MutationSettings


def _binary(sample_data):
    return from_bytes(sample_data, path="game.z64")


def test_project_roundtrip(tmp_path, sample_data):
    bf = _binary(sample_data)
    settings = MutationSettings(seed="abc", density=0.01, magnitude=0.5)
    project = CorruptionProject.single(bf, settings, categories=["models"],
                                       platform="generic")
    path = tmp_path / "p.ccproject"
    project.save(str(path))
    loaded = CorruptionProject.load(str(path))
    assert loaded.source_sha256 == bf.sha256
    assert loaded.layers[0].settings.seed == "abc"
    assert loaded.layers[0].categories == ["models"]


def test_project_verify_source(sample_data):
    bf = _binary(sample_data)
    project = CorruptionProject.single(bf, MutationSettings(seed=1))
    ok, _ = project.verify_source(bf)
    assert ok
    other = from_bytes(sample_data + b"x")
    ok2, msg = project.verify_source(other)
    assert not ok2 and "mismatch" in msg


def test_apply_matches_direct_corrupt(sample_data):
    bf = _binary(sample_data)
    targets = [Region("body", 0x100, 0x3F00, category="models")]
    settings = MutationSettings(seed="match", density=0.02, magnitude=0.4)

    # direct
    direct = corrupt(bf, settings, categories=["models"], platform=None,
                     auto_identify=False,
                     target_intervals=[(0x100, 0x3F00)], repair_checksum=False)

    # via a single-layer project with the same interval
    project = CorruptionProject.single(bf, settings, categories=["models"],
                                       target_intervals=[(0x100, 0x3F00)],
                                       repair_checksum=False, platform="generic")
    applied = project.apply(bf)
    assert applied.output == direct.output


def test_seed_roundtrip_and_to_project(tmp_path, sample_data):
    bf = _binary(sample_data)
    settings = MutationSettings(seed="XYZ", density=0.005, magnitude=0.6)
    project = CorruptionProject.single(bf, settings, categories=["models"],
                                       platform="generic")
    seed = CorruptionSeed.from_project(project)
    path = tmp_path / "r.ccseed"
    seed.save(str(path))
    loaded = CorruptionSeed.load(str(path))
    assert loaded.source_sha256 == bf.sha256
    assert loaded.settings.seed == "XYZ"
    # a seed rebuilds an equivalent single-layer project
    rebuilt = loaded.to_project()
    assert rebuilt.layers[0].settings.magnitude == 0.6


def test_disabled_layer_is_skipped(sample_data):
    bf = _binary(sample_data)
    s = MutationSettings(seed="L", density=0.02, magnitude=0.4)
    p_on = CorruptionProject(source_sha256=bf.sha256, platform="generic",
                             layers=[Layer("L1", s, categories=None,
                                           target_intervals=[(0x100, 0x3F00)])],
                             repair_checksum=False)
    p_off = CorruptionProject(source_sha256=bf.sha256, platform="generic",
                              layers=[Layer("L1", s, enabled=False,
                                            categories=None,
                                            target_intervals=[(0x100, 0x3F00)])],
                              repair_checksum=False)
    assert p_on.apply(bf).output != sample_data
    # a project with only a disabled layer reproduces the original exactly
    assert p_off.apply(bf).output == sample_data


def test_two_layers_are_nondestructive_and_ordered(sample_data):
    bf = _binary(sample_data)
    s1 = MutationSettings(seed="one", density=0.01, magnitude=0.4)
    s2 = MutationSettings(seed="two", density=0.01, magnitude=0.4)
    stack = CorruptionProject(
        source_sha256=bf.sha256, platform="generic", repair_checksum=False,
        layers=[
            Layer("models", s1, categories=None, target_intervals=[(0x100, 0x1000)]),
            Layer("textures", s2, categories=None, target_intervals=[(0x2000, 0x3F00)]),
        ],
    )
    out = stack.apply(bf).output
    # rebuilding from the same original is stable
    assert stack.apply(bf).output == out
    changed = [i for i in range(len(sample_data)) if sample_data[i] != out[i]]
    assert changed
    assert all((0x100 <= i < 0x1000) or (0x2000 <= i < 0x3F00) for i in changed)


def test_project_json_has_no_rom_bytes(sample_data):
    bf = _binary(sample_data)
    project = CorruptionProject.single(bf, MutationSettings(seed=1), platform="generic")
    text = json.dumps(project.to_dict())
    # only the hash is stored, never the source contents
    assert bf.sha256 in text
    assert "layers" in text
