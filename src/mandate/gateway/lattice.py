"""Verdict combination. DENY > UNKNOWN > ALLOW. Rules fail closed.

This is the most important four lines in the system, which is why it lives alone
in its own module with its own tests.
"""
from mandate.gateway.constraints import ALL_EVALUATORS
from mandate.gateway.state import ClauseResult, EvalContext, Verdict

_RANK = {Verdict.ALLOW: 0, Verdict.UNKNOWN: 1, Verdict.DENY: 2}


def combine(results: list[ClauseResult]) -> Verdict:
    return max((r.result for r in results), key=lambda v: _RANK[v], default=Verdict.ALLOW)


def first_blocking(results: list[ClauseResult]) -> ClauseResult | None:
    """The clause to show the agent. Deny outranks unknown; ties break on evaluation order."""
    for want in (Verdict.DENY, Verdict.UNKNOWN):
        for r in results:
            if r.result is want:
                return r
    return None


def evaluate_all(ctx: EvalContext) -> list[ClauseResult]:
    """Every evaluator runs, always. Recording all nine is what makes the log replayable."""
    return [fn(ctx) for fn in ALL_EVALUATORS]
