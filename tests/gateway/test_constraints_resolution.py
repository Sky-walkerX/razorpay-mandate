from mandate.gateway.action import LineItem
from mandate.gateway.constraints import category_deny, merchant_allow, quantity_max_per_item
from mandate.gateway.state import Verdict
from mandate.money import rupees
from mandate.policy.models import ConstraintId as C
from tests.gateway.test_constraints_budget import _ctx  # reuse the builder


def _with(ctx, cid, spec, stated=True):
    ctx.policy.constraints[cid] = spec
    (ctx.policy.provenance.stated if stated else ctx.policy.provenance.inferred).append(cid)
    return ctx

def test_allowed_merchant_passes():
    ctx = _with(_ctx(rupees(100)), C.MERCHANT_ALLOW, ["zepto", "blinkit"])
    assert merchant_allow(ctx).result is Verdict.ALLOW

def test_merchant_that_did_not_resolve_is_unknown_not_deny():
    ctx = _with(_ctx(rupees(100)), C.MERCHANT_ALLOW, ["zepto"])
    ctx.resolved_merchant = None
    assert merchant_allow(ctx).result is Verdict.UNKNOWN

def test_resolved_merchant_outside_the_allowlist_denies():
    ctx = _with(_ctx(rupees(100)), C.MERCHANT_ALLOW, ["zepto"])
    ctx.resolved_merchant = "instamart"
    assert merchant_allow(ctx).result is Verdict.DENY

def test_denied_category_denies():
    ctx = _with(_ctx(rupees(100)), C.CATEGORY_DENY, ["alcohol"])
    ctx.resolved_categories = {"s1": "alcohol"}
    assert category_deny(ctx).result is Verdict.DENY

def test_unresolved_category_is_unknown():
    ctx = _with(_ctx(rupees(100)), C.CATEGORY_DENY, ["alcohol"])
    ctx.resolved_categories = {"s1": None}
    r = category_deny(ctx)
    assert r.result is Verdict.UNKNOWN and "s1" in str(r.detail)

def test_one_unresolved_among_many_still_unknown():
    lines = [LineItem(sku="s1", title="a", qty=1, unit_price=rupees(10), amount=rupees(10)),
             LineItem(sku="s2", title="b", qty=1, unit_price=rupees(10), amount=rupees(10))]
    ctx = _with(_ctx(rupees(0), lines=lines), C.CATEGORY_DENY, ["alcohol"])
    ctx.resolved_categories = {"s1": "grocery", "s2": None}
    assert category_deny(ctx).result is Verdict.UNKNOWN

def test_quantity_over_the_cap_denies():
    lines = [LineItem(sku="s1", title="a", qty=9, unit_price=rupees(10), amount=rupees(90))]
    ctx = _with(_ctx(rupees(0), lines=lines), C.QUANTITY_MAX_PER_ITEM, {"max": 5})
    r = quantity_max_per_item(ctx)
    assert r.result is Verdict.DENY and r.observed == 9
