"""propose() orchestration. The only place the pure evaluator meets the outside world."""
from datetime import datetime
from enum import StrEnum
from pydantic import BaseModel
from mandate.gateway.action import Action, canonical_intent
from mandate.gateway.audit import AuditLog
from mandate.gateway.lattice import evaluate_all, combine, first_blocking
from mandate.gateway.state import AccumulatedState, EvalContext, Verdict
from mandate.policy.models import Policy
from mandate.policy.canonical import policy_hash


class Mode(StrEnum):
    OBSERVE = "observe"   # evaluate and log, do not block. The baseline arm.
    ENFORCE = "enforce"


class Decision(BaseModel):
    verdict: Verdict
    clause_id: str | None = None
    message: str = ""
    idem_key: str = ""
    downstream: dict | None = None
    executed: bool = False


def _explain(clause) -> str:
    if clause is None:
        return "allowed"
    obs, lim = clause.observed, clause.limit
    if isinstance(obs, int) and isinstance(lim, int):
        # Ungrouped rupee formatting: audit messages must contain the plain
        # limit figure (e.g. "2000"), not fmt()'s Indian-grouped "2,000".
        return f"{clause.id}: limit ₹{lim / 100:.2f}, attempted ₹{obs / 100:.2f}"
    return f"{clause.id}: {clause.detail or f'observed {obs}, allowed {lim}'}"


class Gateway:
    def __init__(self, policy: Policy, downstream, audit: AuditLog,
                 mode: Mode = Mode.ENFORCE, resolver=None, ledger=None) -> None:
        self.policy = policy
        self.downstream = downstream
        self.audit = audit
        self.mode = mode
        self.resolver = resolver
        self.ledger = ledger
        self._hash = policy_hash(policy)

    def _state(self) -> AccumulatedState:
        if self.ledger is not None:
            return self.ledger.state()
        return AccumulatedState()

    def _resolve(self, action: Action) -> tuple[str | None, dict[str, str | None]]:
        if self.resolver is None:
            return action.merchant, {i.sku: "grocery" for i in action.items}
        return (self.resolver.merchant(action.merchant),
                {i.sku: self.resolver.category(i.sku, i.title) for i in action.items})

    def propose(self, action: Action, now: datetime) -> Decision:
        idem = canonical_intent(action)
        merchant, categories = self._resolve(action)
        ctx = EvalContext(action=action, policy=self.policy, state=self._state(), now=now,
                          resolved_merchant=merchant, resolved_categories=categories)
        clauses = evaluate_all(ctx)
        verdict = combine(clauses)
        blocking = first_blocking(clauses)

        may_execute = verdict is Verdict.ALLOW or self.mode is Mode.OBSERVE
        downstream_body, executed = None, False
        if may_execute:
            downstream_body = self.downstream.create_order(
                action.amount, receipt=idem, notes={"mandate_id": self.policy.mandate_id})
            executed = True

        self.audit.append(ts=now, mandate_id=self.policy.mandate_id, policy_hash=self._hash,
                          idem_key=idem, action=action, verdict=verdict, clauses=clauses,
                          downstream=downstream_body)
        return Decision(verdict=verdict,
                        clause_id=str(blocking.id) if blocking else None,
                        message=_explain(blocking), idem_key=idem,
                        downstream=downstream_body, executed=executed)
