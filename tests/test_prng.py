"""PRNG determinism and distribution sanity."""

from __future__ import annotations

from controlled_corruptor.core.prng import PRNG_VERSION, Rng, seed_to_u64


def test_same_seed_same_stream():
    a = Rng("CODY-3491281")
    b = Rng("CODY-3491281")
    assert [a.next_u64() for _ in range(100)] == [b.next_u64() for _ in range(100)]


def test_different_seed_different_stream():
    a = [Rng("seed-a").next_u64() for _ in range(50)]
    b = [Rng("seed-b").next_u64() for _ in range(50)]
    assert a != b


def test_int_and_string_seed_paths():
    # int seeds go straight through; strings are hashed. Both are stable.
    assert Rng(12345).next_u64() == Rng(12345).next_u64()
    assert Rng("12345").next_u64() == Rng("12345").next_u64()
    # int 12345 and string "12345" are intentionally different seeds
    assert seed_to_u64(12345) != seed_to_u64("12345")


def test_randbelow_in_range():
    rng = Rng(1)
    for _ in range(1000):
        v = rng.randbelow(7)
        assert 0 <= v < 7


def test_randint_inclusive():
    rng = Rng(2)
    seen = set()
    for _ in range(2000):
        v = rng.randint(-3, 3)
        assert -3 <= v <= 3
        seen.add(v)
    assert seen == set(range(-3, 4))


def test_sample_bits_distinct_count():
    rng = Rng(3)
    for count in range(0, 9):
        mask = rng.sample_bits(count, 8)
        assert bin(mask).count("1") == count


def test_weighted_choice_respects_zero_weight():
    rng = Rng(4)
    picks = [rng.weighted_choice(["a", "b"], [1.0, 0.0]) for _ in range(200)]
    assert set(picks) == {"a"}


def test_version_constant():
    assert PRNG_VERSION == "ccprng-1"
    assert Rng.version == "ccprng-1"
