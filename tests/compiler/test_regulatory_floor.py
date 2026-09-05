"""A statutory floor is not the user's to decline, so it cannot be theirs to omit.

The floor used to live in one hand-written `policies/policy.yaml` and nowhere else.
The compiler never emits `afa.required` -- correctly, because nobody dictating an
intent says "and hold anything above Rs 15,000 for an additional factor" -- and
nothing put it back, so every mandate from `mandate compile`, `/v1/compile` and
`/v1/sandbox` came out without it. Found by running the sandbox: a visitor mandate
authorising Rs 50,000 an order executed Rs 18,600 to the rail with the clause
reading "constraint not in policy".
"""
import json
from datetime import datetime, timedelta

from mandate.compiler.compile import IST, compile_intent
from mandate.policy.models import ConstraintId as C
from mandate.policy.regulatory import AFA_THRESHOLD_PAISE, REGULATORY_FLOOR

EXP = datetime.now(IST) + timedelta(days=30)


class _Scripted:
    """`compile_intent` reads twice and refuses if the readings disagree."""

    model = "scripted-test"

    def __init__(self, reading):
        self._reading = reading

    def next_text(self, system, history):
        return json.dumps(self._reading)


def _compile(constraints, stated):
    provider = _Scripted({
        "constraints": constraints,
        "provenance": {"stated": stated, "inferred": []},
        "questions": [],
    })
    res = compile_intent(
        "spend carefully", principal="p@example.com", agent="a",
        expires=EXP, provider=provider,
    )
    assert res.policy is not None
    return res.policy


def test_a_compiled_mandate_carries_the_floor_the_compiler_never_hears():
    pol = _compile({"budget.total": {"max": 20000000}}, ["budget.total"])

    for cid in REGULATORY_FLOOR:
        assert cid in pol.constraints, f"{cid} missing from a compiled mandate"
    assert pol.constraints[C.AFA_REQUIRED]["threshold"] == AFA_THRESHOLD_PAISE


def test_the_floor_is_attributed_to_the_regulator_and_not_to_the_user():
    """Provenance is what the read-back reads out loud.

    Filing this under `stated` would tell a person they said something no compiler
    heard; under `inferred` it would ask them to confirm a statutory obligation they
    cannot decline. It is neither, which is why the third bucket exists.
    """
    pol = _compile({"budget.total": {"max": 20000000}}, ["budget.total"])

    assert C.AFA_REQUIRED in pol.provenance.regulatory
    assert C.AFA_REQUIRED not in pol.provenance.stated
    assert C.AFA_REQUIRED not in pol.provenance.inferred


def test_a_stricter_threshold_the_user_stated_survives():
    """Asking to be consulted sooner is theirs to choose."""
    pol = _compile(
        {"budget.total": {"max": 20000000}, "afa.required": {"threshold": 500000}},
        ["budget.total", "afa.required"],
    )

    assert pol.constraints[C.AFA_REQUIRED]["threshold"] == 500000
    # They did say it, so it stays theirs.
    assert C.AFA_REQUIRED in pol.provenance.stated
    assert C.AFA_REQUIRED not in pol.provenance.regulatory


def test_a_looser_threshold_does_not_survive():
    """The floor is not theirs to decline, which is the direction "floor" implies.

    Without this, a mandate could raise its own AFA threshold to Rs 1,00,000 and the
    clause a regulator requires would be satisfied by never firing.
    """
    pol = _compile(
        {"budget.total": {"max": 20000000}, "afa.required": {"threshold": 10000000}},
        ["budget.total", "afa.required"],
    )

    assert pol.constraints[C.AFA_REQUIRED]["threshold"] == AFA_THRESHOLD_PAISE
