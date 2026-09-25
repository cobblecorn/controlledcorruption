"""Region model and interval arithmetic."""

from __future__ import annotations

import pytest

from controlled_corruptor.core.regions import (
    Region, merge_intervals, parse_offset, subtract_intervals, total_length,
)


def test_parse_offset_forms():
    assert parse_offset("0x100") == 256
    assert parse_offset("256") == 256
    assert parse_offset(256) == 256
    assert parse_offset("0x01_00") == 256


def test_region_rejects_inverted():
    with pytest.raises(ValueError):
        Region("bad", 0x200, 0x100)


def test_region_matches_by_category_and_tag():
    r = Region("m", 0, 10, category="models", tags=["player", "geometry"])
    assert r.matches(["models"])
    assert r.matches(["player"])
    assert not r.matches(["audio"])
    assert r.matches(None)  # no filter -> everything matches


def test_merge_intervals():
    assert merge_intervals([(0, 5), (4, 8), (20, 22)]) == [(0, 8), (20, 22)]
    assert merge_intervals([(5, 5)]) == []


def test_subtract_intervals_basic():
    got = subtract_intervals([(0, 100)], [(20, 30), (50, 60)])
    assert got == [(0, 20), (30, 50), (60, 100)]


def test_subtract_intervals_full_cover():
    assert subtract_intervals([(10, 20)], [(0, 100)]) == []


def test_subtract_intervals_no_holes():
    assert subtract_intervals([(0, 10), (10, 20)], []) == [(0, 20)]


def test_total_length():
    assert total_length([(0, 10), (20, 25)]) == 15


def test_region_roundtrip():
    r = Region("x", 0x10, 0x20, category="textures", tags=["t"], endianness="big")
    r2 = Region.from_dict(r.to_dict())
    assert (r2.name, r2.start, r2.end, r2.category, r2.tags, r2.endianness) == \
           (r.name, r.start, r.end, r.category, r.tags, r.endianness)
