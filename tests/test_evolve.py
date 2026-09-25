"""Mutation evolution: keep/reject/undo are non-destructive and reproducible."""

from __future__ import annotations

from controlled_corruptor import platforms
from controlled_corruptor.core.binary import from_bytes
from controlled_corruptor.core.evolve import Evolver
from controlled_corruptor.core.settings import MutationSettings
from controlled_corruptor.demo import build_demo_rom


def _evolver():
    bf = from_bytes(build_demo_rom(), path="demo.z64")
    return Evolver(
        binary=bf,
        platform=platforms.detect(bf.data),
        categories=["models"],
        repair_checksum=False,
        base_settings=MutationSettings(density=0.01, magnitude=0.4),
    )


def test_empty_stack_reproduces_original():
    ev = _evolver()
    assert ev.current_output() == ev.binary.data


def test_reject_returns_to_previous_state():
    ev = _evolver()
    before = ev.current_output()
    ev.propose("s1")
    ev.reject()
    assert ev.current_output() == before  # rejecting changes nothing


def test_keep_advances_and_is_cumulative():
    ev = _evolver()
    ev.propose("s1"); ev.keep()
    after_one = ev.current_output()
    assert after_one != ev.binary.data
    ev.propose("s2"); ev.keep()
    after_two = ev.current_output()
    assert after_two != after_one
    assert len(ev.kept) == 2


def test_undo_reverts_last_kept_exactly():
    ev = _evolver()
    ev.propose("s1"); ev.keep()
    snapshot = ev.current_output()
    ev.propose("s2"); ev.keep()
    ev.undo()
    assert ev.current_output() == snapshot  # exact revert, no residue


def test_proposal_is_deterministic():
    ev1 = _evolver()
    ev2 = _evolver()
    c1 = ev1.propose("same-seed")
    c2 = ev2.propose("same-seed")
    assert c1.output == c2.output


def test_export_project_reproduces_output():
    ev = _evolver()
    ev.propose("s1"); ev.keep()
    ev.propose("s2"); ev.keep()
    evolved = ev.current_output()
    project = ev.to_project()
    # applying the exported project to the original reproduces the evolution
    applied = project.apply(ev.binary, verify=True)
    assert applied.output == evolved


def test_keep_without_proposal_errors():
    ev = _evolver()
    try:
        ev.keep()
    except RuntimeError:
        return
    raise AssertionError("expected RuntimeError when keeping with no candidate")
