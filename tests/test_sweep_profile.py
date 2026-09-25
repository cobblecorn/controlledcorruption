"""HeatMap.suggest_regions: merge boot-survivable blocks into draft regions."""

from __future__ import annotations

from controlled_corruptor.core.fuzz import BlockOutcome, HeatMap


def _block(start, end, boot, crash):
    o = BlockOutcome(start, end)
    o.boot = boot
    o.crash = crash
    o.attempts = boot + crash
    return o


def test_suggest_merges_adjacent_safe_blocks():
    heat = HeatMap(blocks=[
        _block(0x0000, 0x1000, boot=10, crash=0),    # safe
        _block(0x1000, 0x2000, boot=10, crash=0),    # safe, adjacent -> merge
        _block(0x2000, 0x3000, boot=0, crash=10),    # critical -> break
        _block(0x3000, 0x4000, boot=9, crash=1),     # safe (0.9)
    ])
    regions = heat.suggest_regions(min_safety=0.9)
    spans = [(r.start, r.end) for r in regions]
    assert (0x0000, 0x2000) in spans      # first two merged
    assert (0x3000, 0x4000) in spans      # last one separate
    assert not any(r.start == 0x2000 for r in regions)  # critical excluded


def test_suggest_confidence_is_average_safety():
    heat = HeatMap(blocks=[
        _block(0x0, 0x100, boot=10, crash=0),   # 1.0
        _block(0x100, 0x200, boot=8, crash=2),  # 0.8 -> below default, excluded
    ])
    regions = heat.suggest_regions(min_safety=0.9)
    assert len(regions) == 1
    assert regions[0].confidence == 1.0


def test_suggest_respects_min_safety_threshold():
    heat = HeatMap(blocks=[_block(0x0, 0x100, boot=7, crash=3)])  # 0.7
    assert heat.suggest_regions(min_safety=0.9) == []
    assert heat.suggest_regions(min_safety=0.6)  # 0.7 passes


def test_suggest_ignores_untested_blocks():
    heat = HeatMap(blocks=[BlockOutcome(0x0, 0x100)])  # attempts == 0
    assert heat.suggest_regions() == []
