from datetime import datetime, timedelta, timezone

import pytest

from mandate.policy.models import CompilerInfo, ConstraintId, Policy, Provenance

IST = timezone(timedelta(hours=5, minutes=30))

def _policy(**over):
    base = {
        "mandate_id": "mnd_01K3F8XQ2R", "principal": "user_8f2", "agent": "agt_test",
        "issued": datetime(2026, 9, 1, 9, 0, tzinfo=IST),
        "expires": datetime(2026, 9, 1, 19, 30, tzinfo=IST),
        "constraints": {ConstraintId.BUDGET_TOTAL: {"max": 200000}},
        "provenance": Provenance(stated=[ConstraintId.BUDGET_TOTAL], inferred=[]),
        "source_text": "under 2000 rupees",
        "compiler": CompilerInfo(model="claude-opus-5", temperature=0.0, version="1.0.0"),
    }
    return Policy(**(base | over))

def test_policy_round_trips():
    assert _policy().constraints[ConstraintId.BUDGET_TOTAL]["max"] == 200000

def test_unknown_constraint_id_is_rejected():
    with pytest.raises(ValueError):
        _policy(constraints={"budget.vibes": {"max": 1}})

def test_every_constraint_must_appear_in_provenance():
    with pytest.raises(ValueError, match="provenance"):
        _policy(provenance=Provenance(stated=[], inferred=[]))

def test_constraint_cannot_be_both_stated_and_inferred():
    with pytest.raises(ValueError, match="both"):
        _policy(provenance=Provenance(stated=[ConstraintId.BUDGET_TOTAL],
                                      inferred=[ConstraintId.BUDGET_TOTAL]))

def test_expires_must_be_after_issued():
    with pytest.raises(ValueError, match="expires"):
        _policy(expires=datetime(2026, 9, 1, 8, 0, tzinfo=IST))

def test_naive_datetimes_are_rejected():
    with pytest.raises(ValueError, match="timezone"):
        _policy(issued=datetime(2026, 9, 1, 9, 0))  # noqa: DTZ001
