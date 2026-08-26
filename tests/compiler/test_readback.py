from mandate.compiler.readback import render
from mandate.policy.models import ConstraintId as C, Provenance
from tests.policy.test_models import _policy

def _p():
    return _policy(
        constraints={C.BUDGET_TOTAL: {"max": 200000},
                     C.BUDGET_PER_ITEM: {"max": 40000},
                     C.CATEGORY_DENY: ["alcohol", "tobacco"]},
        provenance=Provenance(stated=[C.BUDGET_TOTAL, C.CATEGORY_DENY],
                              inferred=[C.BUDGET_PER_ITEM]))

def test_amounts_render_as_rupees_not_paise():
    out = render(_p())
    assert "₹2,000.00" in out and "200000" not in out

def test_inferred_constraints_are_flagged_to_the_user():
    assert "I inferred this" in render(_p())

def test_stated_constraints_are_not_flagged():
    line = [l for l in render(_p()).splitlines() if "₹2,000.00" in l][0]
    assert "I inferred this" not in line

def test_denied_categories_are_listed_in_plain_words():
    assert "alcohol" in render(_p()) and "tobacco" in render(_p())

def test_expiry_is_shown():
    assert "19:30" in render(_p())
