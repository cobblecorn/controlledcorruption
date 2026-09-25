"""Batch generation and the guided-fuzz region sweep (fake tester)."""

from __future__ import annotations

from controlled_corruptor.core import fuzz
from controlled_corruptor.core.batch import generate_batch, seed_series
from controlled_corruptor.core.binary import from_bytes
from controlled_corruptor.core.fuzz import BOOT, CRASH, sweep
from controlled_corruptor.core.settings import MutationSettings
from controlled_corruptor.demo import build_demo_rom


def test_seed_series_forms():
    assert seed_series(3) == [0, 1, 2]
    assert seed_series(3, prefix="RUN-", start=10) == ["RUN-10", "RUN-11", "RUN-12"]


def test_generate_batch_distinct_and_deterministic():
    bf = from_bytes(build_demo_rom(), path="demo.z64")
    settings = MutationSettings(density=0.01, magnitude=0.4)
    seeds = seed_series(5, prefix="s")
    items1 = generate_batch(bf, settings, seeds, categories=["models"])
    items2 = generate_batch(bf, settings, seeds, categories=["models"])
    # deterministic per seed
    assert [i.output for i in items1] == [i.output for i in items2]
    # different seeds -> different outputs
    outs = {bytes(i.output) for i in items1}
    assert len(outs) == len(items1)


def test_sweep_builds_heatmap_with_fake_tester():
    bf = from_bytes(build_demo_rom(), path="demo.z64")

    # Fake tester: any change inside 0x40000..0x50000 "crashes", else "boots".
    critical = (0x40000, 0x50000)
    original = bf.data

    def tester(data: bytes) -> str:
        for i in range(*critical):
            if data[i] != original[i]:
                return CRASH
        return BOOT

    heat = sweep(bf, tester, block_size=0x8000,
                 settings=MutationSettings(density=0.2, magnitude=0.6),
                 repair_checksum=False)
    assert heat.blocks
    # Blocks overlapping the critical range should have low safety.
    crit = heat.critical_blocks(threshold=0.5)
    assert any(b.start < critical[1] and b.end > critical[0] for b in crit)
    # A block well outside the critical range should be safe (boot).
    safe_blocks = [b for b in heat.blocks if b.start >= 0x60000]
    assert safe_blocks and all(b.safety == 1.0 for b in safe_blocks)


def test_sweep_skips_protected_blocks():
    # N64 header/boot (0x0..0x1000) is protected, so no block should start at 0.
    bf = from_bytes(build_demo_rom(), path="demo.z64")

    def tester(_data: bytes) -> str:
        return BOOT

    heat = sweep(bf, tester, block_size=0x1000, repair_checksum=False)
    assert all(b.start >= 0x1000 for b in heat.blocks)


def test_heatmap_render_and_dict():
    bf = from_bytes(build_demo_rom(), path="demo.z64")
    heat = sweep(bf, lambda d: BOOT, block_size=0x40000, repair_checksum=False)
    text = heat.render()
    assert "safety=" in text
    d = heat.to_dict()
    assert "blocks" in d and d["blocks"]


def test_block_outcome_safety_math():
    o = fuzz.BlockOutcome(0, 10)
    for label in (BOOT, BOOT, CRASH):
        o.record(label)
    assert o.attempts == 3 and o.crash == 1
    assert abs(o.safety - (2 / 3)) < 1e-9
