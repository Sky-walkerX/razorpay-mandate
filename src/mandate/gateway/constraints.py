"""The nine constraint evaluators. Pure functions: no I/O, no clock, no model.

Every evaluator returns ALLOW when its constraint is absent from the policy.
Absence means unconstrained, not forbidden.
"""
from mandate.gateway.state import EvalContext, ClauseResult, Verdict
from mandate.policy.models import ConstraintId as C


def _absent(cid: C, ctx: EvalContext) -> ClauseResult | None:
    if cid not in ctx.policy.constraints:
        return ClauseResult(id=cid, result=Verdict.ALLOW, detail="constraint not in policy")
    return None


def budget_total(ctx: EvalContext) -> ClauseResult:
    if (r := _absent(C.BUDGET_TOTAL, ctx)):
        return r
    limit = int(ctx.policy.constraints[C.BUDGET_TOTAL]["max"])
    observed = int(ctx.state.spent) + int(ctx.action.amount)
    return ClauseResult(
        id=C.BUDGET_TOTAL,
        result=Verdict.DENY if observed > limit else Verdict.ALLOW,
        observed=observed, limit=limit,
        detail=f"committed {ctx.state.committed} + pending {ctx.state.pending} "
               f"+ this {int(ctx.action.amount)}")


def budget_per_transaction(ctx: EvalContext) -> ClauseResult:
    if ctx.action.currency != "INR":
        return ClauseResult(id=C.BUDGET_PER_TRANSACTION, result=Verdict.DENY,
                            observed=ctx.action.currency, limit="INR",
                            detail="only INR is supported; no conversion is attempted")
    if (r := _absent(C.BUDGET_PER_TRANSACTION, ctx)):
        return r
    limit = int(ctx.policy.constraints[C.BUDGET_PER_TRANSACTION]["max"])
    observed = int(ctx.action.amount)
    return ClauseResult(id=C.BUDGET_PER_TRANSACTION,
                        result=Verdict.DENY if observed > limit else Verdict.ALLOW,
                        observed=observed, limit=limit)


def budget_per_item(ctx: EvalContext) -> ClauseResult:
    if (r := _absent(C.BUDGET_PER_ITEM, ctx)):
        return r
    limit = int(ctx.policy.constraints[C.BUDGET_PER_ITEM]["max"])
    if not ctx.action.items:
        return ClauseResult(id=C.BUDGET_PER_ITEM, result=Verdict.ALLOW, limit=limit,
                            detail="no line items to check")
    worst = max(ctx.action.items, key=lambda i: int(i.amount))
    observed = int(worst.amount)
    return ClauseResult(id=C.BUDGET_PER_ITEM,
                        result=Verdict.DENY if observed > limit else Verdict.ALLOW,
                        observed=observed, limit=limit, detail=f"worst line {worst.sku}")


def merchant_allow(ctx: EvalContext) -> ClauseResult:
    if (r := _absent(C.MERCHANT_ALLOW, ctx)):
        return r
    allowed = [str(m) for m in ctx.policy.constraints[C.MERCHANT_ALLOW]]
    if ctx.resolved_merchant is None:
        return ClauseResult(id=C.MERCHANT_ALLOW, result=Verdict.UNKNOWN,
                            observed=ctx.action.merchant, limit=allowed,
                            detail="merchant did not resolve to a known id")
    return ClauseResult(id=C.MERCHANT_ALLOW,
                        result=Verdict.ALLOW if ctx.resolved_merchant in allowed
                        else Verdict.DENY,
                        observed=ctx.resolved_merchant, limit=allowed)


def category_deny(ctx: EvalContext) -> ClauseResult:
    if (r := _absent(C.CATEGORY_DENY, ctx)):
        return r
    denied = {str(c) for c in ctx.policy.constraints[C.CATEGORY_DENY]}
    hits, unresolved = [], []
    for item in (ctx.action.items or []):
        cat = ctx.resolved_categories.get(item.sku, None)
        if cat is None:
            unresolved.append(item.sku)
        elif cat in denied:
            hits.append(item.sku)
    if hits:
        return ClauseResult(id=C.CATEGORY_DENY, result=Verdict.DENY, observed=hits,
                            limit=sorted(denied), detail=f"denied category on {hits}")
    if unresolved:
        return ClauseResult(id=C.CATEGORY_DENY, result=Verdict.UNKNOWN, observed=unresolved,
                            limit=sorted(denied), detail=f"unresolved category for {unresolved}")
    return ClauseResult(id=C.CATEGORY_DENY, result=Verdict.ALLOW, limit=sorted(denied))


def quantity_max_per_item(ctx: EvalContext) -> ClauseResult:
    if (r := _absent(C.QUANTITY_MAX_PER_ITEM, ctx)):
        return r
    limit = int(ctx.policy.constraints[C.QUANTITY_MAX_PER_ITEM]["max"])
    if not ctx.action.items:
        return ClauseResult(id=C.QUANTITY_MAX_PER_ITEM, result=Verdict.ALLOW, limit=limit)
    worst = max(ctx.action.items, key=lambda i: i.qty)
    return ClauseResult(id=C.QUANTITY_MAX_PER_ITEM,
                        result=Verdict.DENY if worst.qty > limit else Verdict.ALLOW,
                        observed=worst.qty, limit=limit, detail=f"worst line {worst.sku}")


def velocity(ctx: EvalContext) -> ClauseResult:
    if (r := _absent(C.VELOCITY, ctx)):
        return r
    spec = ctx.policy.constraints[C.VELOCITY]
    limit = int(spec["max_actions"])
    observed = ctx.state.actions_in_window
    return ClauseResult(id=C.VELOCITY,
                        result=Verdict.DENY if observed >= limit else Verdict.ALLOW,
                        observed=observed, limit=limit,
                        detail=f"window={spec.get('window', 'mandate')}")


def time_window(ctx: EvalContext) -> ClauseResult:
    if (r := _absent(C.TIME_WINDOW, ctx)):
        return r
    spec = ctx.policy.constraints[C.TIME_WINDOW]
    after = spec.get("after") or ctx.policy.issued
    before = spec.get("before") or ctx.policy.expires
    ok = after <= ctx.now < before          # expiry is exclusive; ties go to the user
    return ClauseResult(id=C.TIME_WINDOW, result=Verdict.ALLOW if ok else Verdict.DENY,
                        observed=ctx.now.isoformat(),
                        limit=f"[{after.isoformat()}, {before.isoformat()})")


def item_deny_recent(ctx: EvalContext) -> ClauseResult:
    if (r := _absent(C.ITEM_DENY_RECENT, ctx)):
        return r
    spec = ctx.policy.constraints[C.ITEM_DENY_RECENT]
    hits = sorted({i.sku for i in (ctx.action.items or [])} & set(ctx.state.recent_skus))
    return ClauseResult(id=C.ITEM_DENY_RECENT,
                        result=Verdict.DENY if hits else Verdict.ALLOW,
                        observed=hits, limit=f"{spec.get('window_days', 7)}d",
                        detail=f"bought recently: {hits}" if hits else "")


ALL_EVALUATORS = [
    budget_total, budget_per_transaction, budget_per_item,
    merchant_allow, category_deny, item_deny_recent,
    velocity, time_window, quantity_max_per_item,
]
