"""Engine invariants: determinism, bounds, protection, immutability."""

from __future__ import annotations

import pytest

from controlled_corruptor.core import Engine, MutationSettings, Region
from controlled_corruptor.core.settings import ALL_TYPES


def _run(data, targets, protected, **kw):
    settings = MutationSettings(seed="det-seed", density=0.05, magnitude=0.5,
                                types=list(ALL_TYPES), **kw)
    return Engine(settings).run(data, targets=targets, protected=protected)


def test_determinism(sample_data, targets, protected):
    r1 = _run(sample_data, targets, protected)
    r2 = _run(sample_data, targets, protected)
    assert r1.data == r2.data
    assert [rec.describe() for rec in r1.log.records] == \
           [rec.describe() for rec in r2.log.records]


def test_changes_only_inside_mutable_area(sample_data, targets, protected):
    r = _run(sample_data, targets, protected)
    for i in range(len(sample_data)):
        if sample_data[i] != r.data[i]:
            # every changed byte must be in [0x100, 0x3F00)
            assert 0x100 <= i < 0x3F00, f"byte at 0x{i:X} changed outside mutable area"


def test_protected_regions_unchanged(sample_data, targets, protected):
    r = _run(sample_data, targets, protected)
    assert r.data[:0x100] == sample_data[:0x100]
    assert r.data[0x3F00:] == sample_data[0x3F00:]


def test_source_bytes_not_mutated(sample_data, targets, protected):
    original = bytes(sample_data)  # copy for comparison
    _run(sample_data, targets, protected)
    assert sample_data == original  # engine must not touch the input


def test_output_same_length(sample_data, targets, protected):
    r = _run(sample_data, targets, protected)
    assert len(r.data) == len(sample_data)


def test_empty_mutable_area_is_noop(sample_data):
    # target fully covered by protection -> nothing mutable
    targets = [Region("t", 0x100, 0x200, category="models")]
    protected = [Region("p", 0x0, 0x4000, category="header", mutable=False)]
    r = _run(sample_data, targets, protected)
    assert r.mutable_bytes == 0
    assert r.data == sample_data
    assert r.log.summary()["applied"] == 0


def test_density_scales_operation_count(sample_data, targets, protected):
    low = Engine(MutationSettings(seed=1, density=0.001, magnitude=0.3)).run(
        sample_data, targets=targets, protected=protected)
    high = Engine(MutationSettings(seed=1, density=0.02, magnitude=0.3)).run(
        sample_data, targets=targets, protected=protected)
    assert len(high.log.records) > len(low.log.records)


def test_protected_overrides_overlapping_target(sample_data):
    # target and protected overlap; overlap must stay protected
    targets = [Region("t", 0x0, 0x4000, category="models")]
    protected = [Region("p", 0x1000, 0x2000, category="header", mutable=False)]
    r = _run(sample_data, targets, protected)
    assert r.data[0x1000:0x2000] == sample_data[0x1000:0x2000]


def test_prng_version_mismatch_rejected():
    s = MutationSettings(seed=1)
    s.prng_version = "ccprng-999"
    with pytest.raises(ValueError):
        Engine(s)


def test_target_intervals_without_regions(sample_data):
    settings = MutationSettings(seed=7, density=0.05, magnitude=0.4)
    r = Engine(settings).run(sample_data, target_intervals=[(0x800, 0x900)])
    changed = [i for i in range(len(sample_data)) if sample_data[i] != r.data[i]]
    assert changed
    assert all(0x800 <= i < 0x900 for i in changed)
