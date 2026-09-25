"""End-to-end CLI tests via the in-process entry point."""

from __future__ import annotations

import hashlib
import os

from controlled_corruptor.cli.main import main
from controlled_corruptor.demo import build_demo_rom


def _write_demo(tmp_path):
    p = tmp_path / "demo.z64"
    p.write_bytes(build_demo_rom())
    return p


def test_info_runs(tmp_path, capsys):
    demo = _write_demo(tmp_path)
    rc = main(["info", str(demo)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Nintendo 64" in out
    assert "cc-demo-n64" in out


def test_corrupt_is_deterministic_and_confined(tmp_path):
    demo = _write_demo(tmp_path)
    out1 = tmp_path / "a.z64"
    out2 = tmp_path / "b.z64"
    args = ["corrupt", str(demo), "--target", "models", "--seed", "CODY-3491281",
            "--density", "0.01", "--no-repair", "-q", "-o"]
    assert main(args + [str(out1)]) == 0
    assert main(args + [str(out2)]) == 0
    d1 = out1.read_bytes()
    d2 = out2.read_bytes()
    assert d1 == d2  # deterministic

    original = demo.read_bytes()
    changed = [i for i in range(len(original)) if original[i] != d1[i]]
    assert changed
    # models region is 0x40000..0x80000 in the demo profile
    assert all(0x40000 <= i < 0x80000 for i in changed)


def test_corrupt_never_overwrites_source_without_flag(tmp_path):
    demo = _write_demo(tmp_path)
    rc = main(["corrupt", str(demo), "--seed", "1", "-o", str(demo), "-q"])
    assert rc == 2  # refused


def test_save_and_apply_project_roundtrip(tmp_path):
    demo = _write_demo(tmp_path)
    proj = tmp_path / "p.ccproject"
    direct = tmp_path / "direct.z64"
    applied = tmp_path / "applied.z64"

    assert main(["corrupt", str(demo), "--target", "models", "--seed", "s1",
                 "--density", "0.01", "-o", str(direct),
                 "--save-project", str(proj), "-q"]) == 0
    assert main(["apply", str(proj), str(demo), "-o", str(applied), "-q"]) == 0
    assert direct.read_bytes() == applied.read_bytes()


def test_apply_refuses_hash_mismatch(tmp_path):
    demo = _write_demo(tmp_path)
    proj = tmp_path / "p.ccproject"
    main(["corrupt", str(demo), "--seed", "s", "-o", str(tmp_path / "o.z64"),
          "--save-project", str(proj), "-q"])
    wrong = tmp_path / "wrong.z64"
    wrong.write_bytes(b"A" * 2_000_000)
    rc = main(["apply", str(proj), str(wrong), "-o", str(tmp_path / "x.z64"), "-q"])
    assert rc == 2


def test_generic_range_mode(tmp_path):
    blob = tmp_path / "blob.bin"
    blob.write_bytes(bytes(range(256)) * 400)  # 102400 bytes
    out = tmp_path / "blob_c.bin"
    rc = main(["corrupt", str(blob), "--range", "0x1000:0x2000",
               "--type", "byte_replace", "--seed", "42", "-o", str(out), "-q"])
    assert rc == 0
    a, b = blob.read_bytes(), out.read_bytes()
    changed = [i for i in range(len(a)) if a[i] != b[i]]
    assert changed and all(0x1000 <= i < 0x2000 for i in changed)


def test_diff_command(tmp_path, capsys):
    a = tmp_path / "a.bin"
    b = tmp_path / "b.bin"
    data = bytearray(1000)
    a.write_bytes(bytes(data))
    data[500] = 7
    b.write_bytes(bytes(data))
    rc = main(["diff", str(a), str(b)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Changed ranges: 1" in out


def test_profiles_command(capsys):
    rc = main(["profiles"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "cc-demo-n64" in out


def test_implicit_corrupt_subcommand(tmp_path):
    demo = _write_demo(tmp_path)
    out = tmp_path / "imp.z64"
    # no explicit "corrupt" subcommand
    rc = main([str(demo), "--seed", "9", "--target", "models", "-o", str(out), "-q"])
    assert rc == 0
    assert out.exists()


def test_demo_command(tmp_path, capsys):
    out = tmp_path / "d.z64"
    rc = main(["demo", str(out)])
    assert rc == 0
    assert out.exists()
    assert hashlib.sha256(out.read_bytes()).hexdigest() == \
        hashlib.sha256(build_demo_rom()).hexdigest()
