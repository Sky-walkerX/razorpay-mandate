"""propose() orchestration. The only place the pure evaluator meets the outside world."""
import hashlib
import hmac
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from mandate.downstream.fake import DownstreamError, DownstreamTimeout
from mandate.gateway.action import (
    Action,
    Proposal,
    ResolvedAction,
    ResolvedLineItem,
    canonical_intent,
)
from mandate.gateway.audit import AuditLog
from mandate.gateway.idem import EntryState
from mandate.gateway.lattice import combine, evaluate_all, first_blocking
from mandate.gateway.pricebook import PriceBook
from mandate.gateway.state import AccumulatedState, EvalContext, Verdict
from mandate.money import Paise
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
    capability: str | None = None


def _explain(clause) -> str:
    if clause is None:
        return "allowed"
    obs, lim = clause.observed, clause.limit
    if isinstance(obs, int) and isinstance(lim, int):
        return f"{clause.id}: limit ₹{lim / 100:.2f}, attempted ₹{obs / 100:.2f}"
    return f"{clause.id}: {clause.detail or f'observed {obs}, allowed {lim}'}"


def mint_capture_capability(idem_key: str, amount: int, order_id: str, secret: str) -> str:
    """Opaque HMAC capability binding authorized amount to order_id."""
    msg = f"{idem_key}:{amount}:{order_id}".encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def verify_capture_capability(
    capability: str,
    idem_key: str,
    amount: int,
    order_id: str,
    secret: str,
) -> bool:
    expected = mint_capture_capability(idem_key, amount, order_id, secret)
    return hmac.compare_digest(capability, expected)


import threading


class Gateway:
    def __init__(
        self,
        policy: Policy,
        downstream,
        audit: AuditLog,
        mode: Mode = Mode.ENFORCE,
        resolver=None,
        ledger=None,
        pricebook: PriceBook | None = None,
        capability_secret: str = "mandate_gateway_default_secret",
    ) -> None:
        self.policy = policy
        self.downstream = downstream
        self.audit = audit
        self.mode = mode
        self.resolver = resolver
        self.ledger = ledger
        self.pricebook = pricebook
        self.capability_secret = capability_secret
        self._hash = policy_hash(policy)
        self._eval_lock = threading.Lock()

    def _state(self) -> AccumulatedState:
        if self.ledger is not None:
            return self.ledger.state()
        return AccumulatedState()

    def _resolve_to_action(self, prop: Proposal | Action) -> ResolvedAction:
        """Resolve untrusted wire proposal into authoritative ResolvedAction."""
        if isinstance(prop, Proposal):
            items: list[ResolvedLineItem] = []
            for it in prop.items:
                if self.pricebook is not None:
                    pb = self.pricebook.lookup(it.sku)
                    amount = Paise(it.qty * int(pb.unit_price))
                    items.append(
                        ResolvedLineItem(
                            sku=pb.sku,
                            title=pb.title,
                            qty=it.qty,
                            unit_price=pb.unit_price,
                            amount=amount,
                            category=pb.category,
                        )
                    )
                else:
                    items.append(
                        ResolvedLineItem(
                            sku=it.sku,
                            title=it.sku,
                            qty=it.qty,
                            unit_price=Paise(1000),
                            amount=Paise(it.qty * 1000),
                            category="grocery",
                        )
                    )
            total = Paise(sum(int(i.amount) for i in items))
            return ResolvedAction(
                type=prop.type,
                amount=total,
                merchant=prop.merchant,
                items=items,
                attempt=prop.attempt,
                downstream_ref=prop.downstream_ref,
                capability=prop.capability,
            )

        # If already Action, re-verify prices if pricebook is present
        if self.pricebook is not None and prop.items:
            re_items: list[ResolvedLineItem] = []
            for it in prop.items:
                if self.pricebook.has_sku(it.sku):
                    pb = self.pricebook.lookup(it.sku)
                    re_items.append(
                        ResolvedLineItem(
                            sku=pb.sku,
                            title=pb.title,
                            qty=it.qty,
                            unit_price=pb.unit_price,
                            amount=Paise(it.qty * int(pb.unit_price)),
                            category=pb.category,
                        )
                    )
                else:
                    re_items.append(it)
            total = Paise(sum(int(i.amount) for i in re_items))
            return ResolvedAction(
                type=prop.type,
                amount=total,
                merchant=prop.merchant,
                items=re_items,
                attempt=prop.attempt,
                downstream_ref=prop.downstream_ref,
                capability=prop.capability,
            )
        return prop

    def _resolve(self, action: ResolvedAction) -> tuple[str | None, dict[str, str | None]]:
        if self.resolver is None:
            return action.merchant, {i.sku: i.category for i in action.items}
        return (
            self.resolver.merchant(action.merchant),
            {i.sku: self.resolver.category(i.sku, i.title) for i in action.items},
        )

    def propose(self, proposal: Proposal | Action, now: datetime) -> Decision:
        with self._eval_lock:
            try:
                action = self._resolve_to_action(proposal)
            except KeyError as e:
                return Decision(
                    verdict=Verdict.DENY,
                    clause_id="pricebook",
                    message=f"unknown SKU: {e}",
                )

            idem = canonical_intent(action, self.policy.mandate_id)

            # Cached decision: a genuine retry of the same intent must not re-execute.
            if self.ledger is not None and (prior := self.ledger.get(idem)) is not None:
                if prior.state is EntryState.COMMITTED:
                    return Decision(
                        verdict=Verdict.ALLOW,
                        idem_key=idem,
                        downstream=prior.downstream,
                        executed=False,
                        message="already committed; returning cached result",
                    )
                if prior.state is EntryState.FAILED:
                    return Decision(
                        verdict=Verdict.DENY,
                        idem_key=idem,
                        executed=False,
                        clause_id="idempotency",
                        message=f"already failed: {prior.reason}",
                    )
                return Decision(
                    verdict=Verdict.UNKNOWN,
                    idem_key=idem,
                    executed=False,
                    clause_id="idempotency",
                    message="an identical action is in flight and unresolved",
                )

            merchant, categories = self._resolve(action)
            ctx = EvalContext(
                action=action,
                policy=self.policy,
                state=self._state(),
                now=now,
                resolved_merchant=merchant,
                resolved_categories=categories,
            )
            clauses = evaluate_all(ctx)
            verdict = combine(clauses)
            blocking = first_blocking(clauses)

            may_execute = verdict is Verdict.ALLOW or self.mode is Mode.OBSERVE
            if may_execute and self.ledger is not None:
                self.ledger.open_pending(idem, action, now)

        downstream_body, executed, final = None, False, verdict
        cap = None

        if may_execute:
            try:
                downstream_body = self.downstream.create_order(
                    action.amount,
                    receipt=idem,
                    notes={"mandate_id": self.policy.mandate_id},
                    skus=[i.sku for i in action.items],
                )
                executed = True
                if downstream_body and "id" in downstream_body:
                    cap = mint_capture_capability(
                        idem,
                        int(action.amount),
                        downstream_body["id"],
                        self.capability_secret,
                    )
                    downstream_body["capability"] = cap
                if self.ledger is not None:
                    self.ledger.mark_committed(idem, downstream_body)
            except DownstreamTimeout:
                final = Verdict.UNKNOWN
            except DownstreamError as e:
                final = Verdict.DENY
                if self.ledger is not None:
                    self.ledger.mark_failed(idem, str(e))

        self.audit.append(
            ts=now,
            mandate_id=self.policy.mandate_id,
            policy_hash=self._hash,
            idem_key=idem,
            action=action,
            verdict=final,
            clauses=clauses,
            downstream=downstream_body,
        )
        return Decision(
            verdict=final,
            clause_id=(
                str(blocking.id)
                if blocking
                else (None if final is Verdict.ALLOW else "downstream")
            ),
            message=_explain(blocking) if blocking else str(final),
            idem_key=idem,
            downstream=downstream_body,
            executed=executed,
            capability=cap,
        )


