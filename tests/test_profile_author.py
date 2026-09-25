"""User profile authoring: mkprofile / addregion and the underlying helpers."""

from __future__ import annotations

import hashlib

from controlled_corruptor.cli.main import main
from controlled_corruptor.core.binary import from_bytes
from controlled_corruptor.demo import build_demo_rom
from controlled_corruptor.profiles import ProfileLibrary, author


def test_parse_region_spec_full():
    r = author.parse_region_spec("Models:models:0x40000:0x80000:big:float32")
    assert r.name == "Models" and r.category == "models"
    assert r.start == 0x40000 and r.end == 0x80000
    assert r.endianness == "big" and r.data_type == "float32"


def test_parse_region_spec_minimal():
    r = author.parse_region_spec("A:audio:0x10:0x20")
    assert r.endianness == "little" and r.data_type is None


def test_new_profile_uses_hash():
    bf = from_bytes(build_demo_rom(), path="demo.z64")
    p = author.new_profile(bf, "mine", "Mine", platform="n64")
    assert p.identify(bf.sha256)


def test_mkprofile_cli_and_identify(tmp_path):
    demo = tmp_path / "demo.z64"
    demo.write_bytes(build_demo_rom())
    out = tmp_path / "mine.json"
    rc = main(["mkprofile", str(demo), "--id", "mine", "--name", "Mine",
               "--region", "Models:models:0x40000:0x80000:big:float32",
               "-o", str(out), "-q"])
    assert rc == 0 and out.exists()

    # a library pointed at tmp_path should identify the demo ROM via this profile
    lib = ProfileLibrary(dirs=[str(tmp_path)])
    sha = hashlib.sha256(build_demo_rom()).hexdigest()
    prof = lib.identify(sha)
    assert prof is not None and prof.id == "mine"
    assert "models" in prof.categories()


def test_addregion_cli(tmp_path):
    demo = tmp_path / "demo.z64"
    demo.write_bytes(build_demo_rom())
    out = tmp_path / "mine.json"
    main(["mkprofile", str(demo), "--id", "mine", "-o", str(out), "-q"])
    rc = main(["addregion", str(out), "--name", "Audio", "--category", "audio",
               "--range", "0x100000:0x120000", "-q"])
    assert rc == 0
    prof = author.load_profile(str(out))
    assert any(r.name == "Audio" and r.category == "audio" for r in prof.regions)


def test_mkprofile_from_diff(tmp_path):
    a = build_demo_rom()
    b = bytearray(a)
    for i in range(0x50000, 0x50040):
        b[i] ^= 0xFF
    fa = tmp_path / "a.z64"
    fb = tmp_path / "b.z64"
    fa.write_bytes(a)
    fb.write_bytes(bytes(b))
    out = tmp_path / "diff.json"
    rc = main(["mkprofile", str(fa), "--id", "d", "--from-diff", str(fb),
               "-o", str(out), "-q"])
    assert rc == 0
    prof = author.load_profile(str(out))
    assert prof.regions  # at least one diff region
    assert any(r.start <= 0x50000 < r.end for r in prof.regions)
