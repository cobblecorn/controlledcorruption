"""End-to-end integration: the 'proof of architecture' demonstration.

Load a ROM -> recognize its profile -> corrupt only Character Models at a
deterministic seed/intensity -> confirm the corruption is confined to the
model data (and checksum), the ROM checksum is valid afterwards, the result is
reproducible, and a saved project reproduces it byte-for-byte.
"""

from __future__ import annotations

from controlled_corruptor import platforms
from controlled_corruptor.core.binary import from_bytes
from controlled_corruptor.core.pipeline import corrupt
from controlled_corruptor.core.project import CorruptionProject
from controlled_corruptor.core.settings import MutationSettings
from controlled_corruptor.demo import build_demo_rom
from controlled_corruptor.profiles import ProfileLibrary

MODELS = (0x40000, 0x80000)
CHECKSUM = (0x10, 0x18)


def test_full_demonstration():
    binary = from_bytes(build_demo_rom(), path="demo.z64")

    # 1) recognize platform + profile
    plat = platforms.detect(binary.data)
    assert plat.id == "n64"
    profile = ProfileLibrary().identify(binary.sha256)
    assert profile is not None and "models" in profile.categories()

    # 2) corrupt ONLY Character Models, deterministic seed + intensity
    settings = MutationSettings.from_intensity(0.4, seed="CODY-3491281")
    result = corrupt(binary, settings, categories=["models"], profile=profile)

    # 3) changes confined to the models region (+ recalculated checksum)
    changed = [i for i in range(binary.size)
               if binary.data[i] != result.output[i]]
    assert changed
    assert all((MODELS[0] <= i < MODELS[1]) or (CHECKSUM[0] <= i < CHECKSUM[1])
               for i in changed)

    # 4) header (minus the recalculated checksum words) and boot code untouched
    assert result.output[:CHECKSUM[0]] == binary.data[:CHECKSUM[0]]
    assert result.output[CHECKSUM[1]:0x1000] == binary.data[CHECKSUM[1]:0x1000]

    # 5) checksum valid after corruption
    report = plat.validate(result.output)
    checks = {c.name: c.level.value for c in report.checks}
    assert checks.get("n64.checksum") == "PASS"
    assert result.checksum_repaired

    # 6) reproducible
    again = corrupt(binary, MutationSettings.from_intensity(0.4, seed="CODY-3491281"),
                    categories=["models"], profile=profile)
    assert again.output == result.output

    # 7) a saved project reproduces it byte-for-byte
    project = CorruptionProject.single(
        binary, settings, categories=["models"],
        profile_id=profile.id, platform="n64")
    assert project.apply(binary).output == result.output


def test_generic_mode_on_non_rom():
    # A non-ROM binary still works in Generic mode, confined to the range.
    data = bytes(range(256)) * 512
    binary = from_bytes(data, path="blob.bin")
    settings = MutationSettings(seed="g", density=0.05, magnitude=0.6)
    result = corrupt(binary, settings, target_intervals=[(0x2000, 0x4000)],
                     auto_identify=False, repair_checksum=False)
    changed = [i for i in range(len(data)) if data[i] != result.output[i]]
    assert changed and all(0x2000 <= i < 0x4000 for i in changed)
