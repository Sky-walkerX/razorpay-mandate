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
