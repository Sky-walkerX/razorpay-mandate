"""propose() orchestration. The only place the pure evaluator meets the outside world."""
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from mandate.downstream.fake import DownstreamError, DownstreamTimeout
from mandate.gateway.action import Action, canonical_intent
from mandate.gateway.audit import AuditLog
from mandate.gateway.idem import EntryState
from mandate.gateway.lattice import combine, evaluate_all, first_blocking
from mandate.gateway.state import AccumulatedState, EvalContext, Verdict
from mandate.policy.canonical import policy_hash
from mandate.policy.models import Policy


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

        # Cached decision: a genuine retry of the same intent must not re-execute.
        if self.ledger is not None and (prior := self.ledger.get(idem)) is not None:
            if prior.state is EntryState.COMMITTED:
                return Decision(verdict=Verdict.ALLOW, idem_key=idem,
                                downstream=prior.downstream, executed=False,
                                message="already committed; returning cached result")
            if prior.state is EntryState.FAILED:
                return Decision(verdict=Verdict.DENY, idem_key=idem, executed=False,
                                clause_id="idempotency",
                                message=f"already failed: {prior.reason}")
            return Decision(verdict=Verdict.UNKNOWN, idem_key=idem, executed=False,
                            clause_id="idempotency",
                            message="an identical action is in flight and unresolved")

        may_execute = verdict is Verdict.ALLOW or self.mode is Mode.OBSERVE
        downstream_body, executed, final = None, False, verdict
        if may_execute:
            if self.ledger is not None:
                self.ledger.open_pending(idem, action, now)
            try:
                downstream_body = self.downstream.create_order(
                    action.amount, receipt=idem,
                    notes={"mandate_id": self.policy.mandate_id})
                executed = True
                if self.ledger is not None:
                    self.ledger.mark_committed(idem, downstream_body)
            except DownstreamTimeout:
                final = Verdict.UNKNOWN     # held PENDING for the reconciler
            except DownstreamError as e:
                final = Verdict.DENY
                if self.ledger is not None:
                    self.ledger.mark_failed(idem, str(e))

        self.audit.append(ts=now, mandate_id=self.policy.mandate_id, policy_hash=self._hash,
                          idem_key=idem, action=action, verdict=final, clauses=clauses,
                          downstream=downstream_body)
        return Decision(verdict=final,
                        clause_id=str(blocking.id) if blocking else
                        (None if final is Verdict.ALLOW else "downstream"),
                        message=_explain(blocking) if blocking else str(final),
                        idem_key=idem, downstream=downstream_body, executed=executed)
