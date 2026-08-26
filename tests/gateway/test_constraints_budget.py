from datetime import datetime, timezone, timedelta
from mandate.gateway.constraints import budget_total, budget_per_transaction, budget_per_item
from mandate.gateway.state import AccumulatedState, EvalContext, Verdict
from mandate.gateway.action import Action, LineItem, ActionType
from mandate.money import rupees
from mandate.policy.models import ConstraintId as C
from tests.policy.test_models import _policy

IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime(2026, 9, 1, 12, 0, tzinfo=IST)


def _ctx(amount, *, committed=0, pending=0, per_item_max=None, lines=None):
    cons = {C.BUDGET_TOTAL: {"max": 200000}, C.BUDGET_PER_TRANSACTION: {"max": 200000}}
    prov_stated = [C.BUDGET_TOTAL, C.BUDGET_PER_TRANSACTION]
    if per_item_max is not None:
        cons[C.BUDGET_PER_ITEM] = {"max": per_item_max}
        prov_stated.append(C.BUDGET_PER_ITEM)
    from mandate.policy.models import Provenance
    pol = _policy(constraints=cons, provenance=Provenance(stated=prov_stated, inferred=[]))
    items = lines or [LineItem(sku="s1", title="t", qty=1, unit_price=amount, amount=amount)]
    act = Action(type=ActionType.CREATE_ORDER, amount=rupees(0) + sum(i.amount for i in items),
                 merchant="zepto", items=items)
    st = AccumulatedState(committed=committed, pending=pending, action_count=0,
                          recent_skus=set(), actions_in_window=0)
    return EvalContext(action=act, policy=pol, state=st, now=NOW,
                       resolved_merchant="zepto", resolved_categories={"s1": "grocery"})


def test_under_total_allows():
    assert budget_total(_ctx(rupees(500))).result is Verdict.ALLOW

def test_over_total_denies():
    assert budget_total(_ctx(rupees(2500))).result is Verdict.DENY

def test_pending_spend_counts_against_the_budget():
    """Counting only committed spend lets a burst of in-flight orders each see full budget."""
    r = budget_total(_ctx(rupees(600), committed=rupees(800), pending=rupees(700)))
    assert r.result is Verdict.DENY
    assert r.observed == rupees(800) + rupees(700) + rupees(600)

def test_exactly_at_the_limit_allows():
    assert budget_total(_ctx(rupees(2000))).result is Verdict.ALLOW

def test_per_transaction_denies_a_single_large_action():
    assert budget_per_transaction(_ctx(rupees(50000))).result is Verdict.DENY

def test_per_item_denies_one_expensive_line():
    lines = [LineItem(sku="s1", title="a", qty=1, unit_price=rupees(100), amount=rupees(100)),
             LineItem(sku="s2", title="b", qty=1, unit_price=rupees(900), amount=rupees(900))]
    r = budget_per_item(_ctx(rupees(0), per_item_max=40000, lines=lines))
    assert r.result is Verdict.DENY and r.observed == rupees(900)

def test_absent_constraint_allows():
    assert budget_per_item(_ctx(rupees(500))).result is Verdict.ALLOW

def test_non_inr_currency_denies_on_per_transaction():
    ctx = _ctx(rupees(100))
    ctx.action.currency = "USD"
    assert budget_per_transaction(ctx).result is Verdict.DENY
