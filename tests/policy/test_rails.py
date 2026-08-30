"""The rail projection makes a claim about other people's specs. Pin it."""
from pathlib import Path

import pytest

from mandate.policy.loader import load as load_policy
from mandate.policy.models import ConstraintId as C
from mandate.policy.rails import (
    AP2_CARRIES,
    RESERVE_PAY_CARRIES,
    diff,
    to_ap2_intent_mandate,
    to_ap2_payment_constraints,
    to_reserve_pay,
)


@pytest.fixture
def policy():
    return load_policy(Path(__file__).resolve().parents[2] / "policies" / "policy.yaml")


def test_every_constraint_type_has_a_verdict_on_both_rails():
    """A clause missing from a table would silently read as 'lost'. Make that impossible."""
    for cid in C:
        assert cid in AP2_CARRIES, f"{cid} has no AP2 mapping"
        assert cid in RESERVE_PAY_CARRIES, f"{cid} has no Reserve Pay mapping"


def test_reserve_pay_holds_exactly_amount_merchant_expiry():
    held = {c for c, (kind, _) in RESERVE_PAY_CARRIES.items() if kind == "rail"}
    assert held == {C.BUDGET_TOTAL, C.MERCHANT_ALLOW, C.TIME_WINDOW}


def test_ap2_holds_five_of_the_nine_structurally():
    held = {c for c, (kind, _) in AP2_CARRIES.items() if kind == "ap2"}
    assert held == {
        C.BUDGET_TOTAL,
        C.BUDGET_PER_TRANSACTION,
        C.MERCHANT_ALLOW,
        C.TIME_WINDOW,
        C.VELOCITY,
    }


def test_the_clauses_no_rail_can_hold():
    """These four are the product. If a rail ever gains one, this test should fail."""
    for cid in (C.BUDGET_PER_ITEM, C.QUANTITY_MAX_PER_ITEM, C.ITEM_DENY_RECENT):
        assert AP2_CARRIES[cid][0] == "none"
        assert RESERVE_PAY_CARRIES[cid][0] == "none"
    # category.deny survives only as words nothing evaluates.
    assert AP2_CARRIES[C.CATEGORY_DENY][0] == "prose"
    assert RESERVE_PAY_CARRIES[C.CATEGORY_DENY][0] == "none"


def test_intent_mandate_uses_the_real_ap2_field_names(policy):
    m = to_ap2_intent_mandate(policy)
    assert set(m) == {
        "natural_language_description",
        "merchants",
        "intent_expiry",
        "user_cart_confirmation_required",
        "requires_refundability",
    }
    assert m["natural_language_description"] == policy.source_text
    assert "zepto" in m["merchants"]


def test_the_alcohol_rule_survives_only_as_prose(policy):
    """The strongest single line in the demo: it is in the text, and nothing reads it."""
    m = to_ap2_intent_mandate(policy)
    assert "alcoholic" in m["natural_language_description"].lower()
    structured = to_ap2_payment_constraints(policy)
    blob = str(structured).lower()
    assert "alcohol" not in blob


def test_payment_constraints_carry_the_budget_and_velocity(policy):
    types = {c["type"] for c in to_ap2_payment_constraints(policy)}
    assert "payment.budget" in types
    assert "payment.agent_recurrence" in types
    assert "payment.allowed_payee" in types


def test_reserve_pay_cannot_hold_a_three_merchant_allowlist(policy):
    rp = to_reserve_pay(policy)
    assert rp["payee"] == "zepto"
    # The other two do not fit in one block, and are reported rather than dropped.
    assert rp["payee_overflow"] == ["blinkit", "instamart"]


def test_diff_counts_what_each_rail_loses(policy):
    d = diff(policy)
    assert d.total_clauses == len(policy.constraints)
    assert d.ap2_held < d.total_clauses
    assert d.reserve_pay_held < d.ap2_held
    assert d.reserve_pay_lost > d.ap2_lost
