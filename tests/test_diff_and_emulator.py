"""Differential analysis and the custom emulator command builder."""

from __future__ import annotations

import os

from controlled_corruptor.core.diff import changed_intervals, diff_summary
from controlled_corruptor.emulator import CustomCommandEmulator


def test_diff_identical_is_empty():
    a = bytes(1000)
    assert changed_intervals(a, a) == []


def test_diff_reports_changed_ranges():
    a = bytearray(1000)
    b = bytearray(1000)
    b[100] = 1
    b[101] = 2
    b[500] = 9
    intervals = changed_intervals(bytes(a), bytes(b), merge_gap=4)
    assert (100, 102) in intervals
    assert any(s <= 500 < e for s, e in intervals)


def test_diff_merges_within_gap():
    a = bytearray(100)
    b = bytearray(100)
    b[10] = 1
    b[13] = 1  # within merge_gap of the first
    intervals = changed_intervals(bytes(a), bytes(b), merge_gap=8)
    assert intervals == [(10, 14)]


def test_diff_length_mismatch():
    s = diff_summary(bytes(10), bytes(20))
    assert s["size_a"] == 10 and s["size_b"] == 20
    assert s["changed_bytes"] >= 10


def test_emulator_substitutes_rom_placeholder():
    emu = CustomCommandEmulator('"/opt/emu/run" --rom "{ROM}" --fast')
    args = emu.build_args("/games/demo.z64")
    assert args[0] == "/opt/emu/run"
    assert os.path.abspath("/games/demo.z64") in args


def test_emulator_appends_rom_when_no_placeholder():
    emu = CustomCommandEmulator("emulator --start")
    args = emu.build_args("/games/demo.z64")
    assert args[-1] == os.path.abspath("/games/demo.z64")


def test_emulator_dict_roundtrip():
    emu = CustomCommandEmulator("run {ROM}", name="Test", timeout=5.0)
    emu2 = CustomCommandEmulator.from_dict(emu.to_dict())
    assert emu2.command == "run {ROM}"
    assert emu2.timeout == 5.0
