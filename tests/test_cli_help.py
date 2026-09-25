"""Smoke test: every subcommand's --help parses and exits cleanly."""

from __future__ import annotations

import pytest

from controlled_corruptor.cli.main import SUBCOMMANDS, build_parser, main


def test_all_subcommands_registered_have_help():
    parser = build_parser()
    # argparse stores the subparsers action; collect its choices
    subparsers = [a for a in parser._actions
                  if a.__class__.__name__ == "_SubParsersAction"]
    assert subparsers, "no subparsers found"
    choices = set(subparsers[0].choices)
    # every advertised subcommand must be a registered parser
    assert SUBCOMMANDS <= choices, SUBCOMMANDS - choices


@pytest.mark.parametrize("cmd", sorted(SUBCOMMANDS))
def test_subcommand_help_exits_zero(cmd):
    with pytest.raises(SystemExit) as exc:
        main([cmd, "--help"])
    assert exc.value.code == 0


def test_top_level_help():
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


def test_no_command_prints_help_and_returns_1():
    assert main([]) == 1


def test_version():
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
