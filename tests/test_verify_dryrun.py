"""`verify` command and `corrupt --dry-run`."""

from __future__ import annotations

from controlled_corruptor.cli.main import main
from controlled_corruptor.demo import build_demo_rom


def _demo(tmp_path):
    p = tmp_path / "demo.z64"
    p.write_bytes(build_demo_rom())
    return p


def test_dry_run_writes_nothing(tmp_path, capsys):
    demo = _demo(tmp_path)
    out = tmp_path / "out.z64"
    rc = main(["corrupt", str(demo), "-t", "models", "--seed", "1",
               "--dry-run", "-o", str(out)])
    assert rc == 0
    assert not out.exists()  # dry-run must not write
    err = capsys.readouterr().err
    assert "DRY-RUN" in err


def test_verify_project_roundtrip(tmp_path, capsys):
    demo = _demo(tmp_path)
    out = tmp_path / "out.z64"
    proj = tmp_path / "p.ccproject"
    main(["corrupt", str(demo), "-t", "models", "--seed", "V1",
          "-o", str(out), "--save-project", str(proj), "-q"])

    rc = main(["verify", str(proj), str(demo), "--against", str(out)])
    assert rc == 0
    err = capsys.readouterr().err
    assert "source hash matches" in err
    assert "deterministic reproduction" in err
    assert f"output matches {out}" in err


def test_verify_detects_wrong_source(tmp_path, capsys):
    demo = _demo(tmp_path)
    proj = tmp_path / "p.ccproject"
    main(["corrupt", str(demo), "--seed", "x", "-o", str(tmp_path / "o.z64"),
          "--save-project", str(proj), "-q"])
    wrong = tmp_path / "wrong.z64"
    wrong.write_bytes(b"Z" * 2_000_000)
    rc = main(["verify", str(proj), str(wrong)])
    assert rc == 1
    assert "FAIL" in capsys.readouterr().err


def test_verify_seed_file(tmp_path):
    demo = _demo(tmp_path)
    out = tmp_path / "out.z64"
    seed = tmp_path / "r.ccseed"
    main(["corrupt", str(demo), "-t", "models", "--seed", "S9",
          "-o", str(out), "--save-seed", str(seed), "-q"])
    rc = main(["verify", str(seed), str(demo), "--against", str(out)])
    assert rc == 0


def test_verify_against_mismatch(tmp_path, capsys):
    demo = _demo(tmp_path)
    proj = tmp_path / "p.ccproject"
    main(["corrupt", str(demo), "-t", "models", "--seed", "A",
          "-o", str(tmp_path / "a.z64"), "--save-project", str(proj), "-q"])
    # compare against the untouched source -> should NOT match
    rc = main(["verify", str(proj), str(demo), "--against", str(demo)])
    assert rc == 1
    assert "does NOT match" in capsys.readouterr().err
