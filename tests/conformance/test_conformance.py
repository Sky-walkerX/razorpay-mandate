"""Pytest wrapper for the eight-attack conformance suite.

`mandate conformance` writes the report the writeup and the demo read. This runs
the same attack objects so a regression fails the build rather than waiting for
the next manual run. Neither path calls a language model.
"""
import pytest

from mandate.conformance.suite import ATTACKS, run_conformance_suite
from mandate.conformance.witness import ConformanceOutcome

# The suite runs 200 trials on stage; CI runs fewer so the wrapper stays fast.
# The trial count is the only thing that differs.
CI_TRIALS = 40


@pytest.fixture(scope="module")
def results(tmp_path_factory):
    return run_conformance_suite(tmp_path_factory.mktemp("conformance"), trials=CI_TRIALS)


def test_the_suite_runs_all_nine_attacks(results):
    assert len(results) == len(ATTACKS) == 9
    assert {r.attack_id for r in results} == {
        "replay.token", "replay.intent", "idem.forge", "race.velocity",
        "race.budget", "capture.divergence", "delegate.split", "escalate.self",
        "rail.divergence",
    }


def test_no_attack_is_vacuous(results):
    """A vacuous attack is a suite that has quietly stopped testing anything.

    This is Day 16 at a different layer: an empty room scored 100% containment
    once, and a suite that blocks attacks that were never possible is the same bug.
    """
    vacuous = [r.attack_id for r in results if r.outcome is ConformanceOutcome.VACUOUS]
    assert not vacuous, f"witness never fired for: {vacuous}"


def test_every_attack_is_blocked(results):
    escaped = [(r.attack_id, r.detail) for r in results
               if r.outcome is ConformanceOutcome.ESCAPED]
    assert not escaped, f"real holes: {escaped}"


def test_conformance_rows_carry_no_model_field(results):
    """Conformance rows must never be mistaken for containment rows by score()."""
    for r in results:
        assert not hasattr(r, "model")
        assert "model" not in vars(r)
