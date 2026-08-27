from datetime import datetime

import pytest

from mandate.compiler.compile import IST
from mandate.money import rupees
from mandate.policy.models import CompilerInfo, Policy, Provenance
from mandate.policy.models import ConstraintId as C


@pytest.fixture
def policy_all_nine() -> Policy:
    """A policy that exercises every constraint an attack family targets."""
    base = {
        C.BUDGET_TOTAL: {"max": int(rupees(2000))},
        C.BUDGET_PER_TRANSACTION: {"max": int(rupees(1000))},
        C.BUDGET_PER_ITEM: {"max": int(rupees(500))},
        C.MERCHANT_ALLOW: ["zepto", "blinkit", "instamart"],
        C.CATEGORY_DENY: ["alcohol"],
        C.QUANTITY_MAX_PER_ITEM: {"max": 5},
        C.VELOCITY: {"max_actions": 3, "window": "mandate"},
        C.TIME_WINDOW: {},
    }
    return Policy(
        mandate_id="mnd_test",
        principal="user_local",
        agent="agt_shopper",
        issued=datetime(2026, 9, 1, 9, 0, tzinfo=IST),
        expires=datetime(2026, 9, 1, 19, 30, tzinfo=IST),
        source_text="test",
        constraints=base,
        provenance=Provenance(stated=list(base.keys()), inferred=[]),
        compiler=CompilerInfo(model="claude-opus-5", temperature=0.0, version="1.0.0"),
    )
