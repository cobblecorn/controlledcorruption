"""Emulator preset persistence, resolution and CLI."""

from __future__ import annotations

import os

import pytest

from controlled_corruptor.cli.main import main
from controlled_corruptor.emulator import CustomCommandEmulator
from controlled_corruptor.emulator.config import EmulatorPresets, resolve_launch


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CCORRUPT_CONFIG_DIR", str(tmp_path))
    return tmp_path


def test_add_get_default_persist(config_dir):
    p = EmulatorPresets()
    p.add("dolphin", '"Dolphin.exe" "{ROM}"')
    p.add("retroarch", 'retroarch -L core.so {ROM}')
    p.save()
    # first added becomes default
    assert p.default() == "dolphin"

    reloaded = EmulatorPresets()
    assert set(reloaded.names()) == {"dolphin", "retroarch"}
    assert reloaded.resolve_command("retroarch").startswith("retroarch")


def test_remove_reassigns_default(config_dir):
    p = EmulatorPresets()
    p.add("a", "a {ROM}", make_default=True)
    p.add("b", "b {ROM}")
    p.remove("a")
    p.save()
    assert p.default() == "b"


def test_resolve_launch_at_preset(config_dir):
    p = EmulatorPresets()
    p.add("emu", 'run "{ROM}"')
    p.save()
    assert resolve_launch("@emu") == 'run "{ROM}"'
    # non-@ passes through verbatim
    assert resolve_launch("literal {ROM}") == "literal {ROM}"


def test_resolve_missing_preset_raises(config_dir):
    with pytest.raises(KeyError):
        resolve_launch("@nope")


def test_make_adapter_builds_command(config_dir):
    p = EmulatorPresets()
    p.add("emu", 'run --rom "{ROM}"')
    adapter = p.make_adapter("emu")
    assert isinstance(adapter, CustomCommandEmulator)
    args = adapter.build_args("/games/x.z64")
    assert os.path.abspath("/games/x.z64") in args


def test_cli_emu_add_list_default_remove(config_dir, capsys):
    assert main(["emu", "add", "dolphin", '"Dolphin.exe" {ROM}']) == 0
    assert main(["emu", "add", "pj64", 'Project64.exe {ROM}']) == 0
    assert main(["emu", "default", "pj64"]) == 0
    main(["emu", "list"])
    out = capsys.readouterr().out
    assert "dolphin" in out and "pj64" in out
    assert "* pj64" in out or "*pj64" in out or " *pj64" in out

    assert main(["emu", "remove", "dolphin"]) == 0
    assert main(["emu", "remove", "ghost"]) == 2  # not found
