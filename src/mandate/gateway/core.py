"""propose() orchestration. The only place the pure evaluator meets the outside world."""
import hashlib
import hmac
import threading
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel

from mandate.downstream.fake import DownstreamError, DownstreamTimeout
from mandate.gateway.action import (
    Action,
    Proposal,
    RawProposal,
    ResolvedAction,
    ResolvedLineItem,
    canonical_intent,
)
from mandate.gateway.audit import AuditLog
from mandate.gateway.idem import EntryState
from mandate.gateway.lattice import combine, evaluate_all, first_blocking
from mandate.gateway.pricebook import PriceBook
from mandate.gateway.quote import (
    MerchantKeyring,
    QuoteDisagrees,
    QuoteError,
    verify_quote,
)
from mandate.gateway.revocation import RevocationList
from mandate.gateway.state import AccumulatedState, ClauseResult, EvalContext, Verdict
from mandate.gateway.tokens import TokenError, verify_agent_token
from mandate.money import Paise
from mandate.policy.canonical import policy_hash
from mandate.policy.crypto import SignatureInvalid
from mandate.policy.models import ConstraintId as C
from mandate.policy.models import Policy


class PriceBookMissing(Exception):
    """The gateway was asked to resolve a proposal with no price book to resolve it from."""


class TokenRejected(Exception):
    """A presented agent token failed verification, expiry, binding or revocation."""


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


# Clauses whose observed/limit pair counts things rather than measuring money.
# Without this, `velocity: limit 3` renders as "limit \u20b90.03", which is both wrong
# and fed straight back to the agent as the reason it was refused.
_COUNT_CLAUSES = frozenset({C.VELOCITY, C.QUANTITY_MAX_PER_ITEM})


def _explain(clause) -> str:
    if clause is None:
        return "allowed"
    obs, lim = clause.observed, clause.limit
    if isinstance(obs, int) and isinstance(lim, int):
        if clause.id in _COUNT_CLAUSES:
            unit = "orders" if clause.id == C.VELOCITY else "per item"
            return f"{clause.id}: limit {lim} {unit}, attempted {obs}"
        return f"{clause.id}: limit \u20b9{lim / 100:.2f}, attempted \u20b9{obs / 100:.2f}"
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


def _strip_quotes(prop: Proposal | Action) -> Proposal:
    if not hasattr(prop, "items") or not prop.items:
        return prop  # type: ignore[return-value]
    return prop.model_copy(
        update={"items": [it.model_copy(update={"quote": None}) for it in prop.items]}
    )


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
        capability_secret: str | None = None,
        issuer_public_key: str | None = None,
        revocations: RevocationList | None = None,
        approvals=None,
        merchant_keyring: MerchantKeyring | None = None,
    ) -> None:
        if not capability_secret:
            raise ValueError("capability_secret is required and cannot be empty")
        self.policy = policy
        self.downstream = downstream
        self.audit = audit
        self.mode = mode
        self.resolver = resolver
        self.ledger = ledger
        self.pricebook = pricebook
        self.capability_secret = capability_secret
        # The gateway holds the issuer's PUBLIC key only. It can verify a token
        # and it cannot mint one, which is what makes escalate.self impossible
        # rather than merely unimplemented.
        self.issuer_public_key = issuer_public_key
        self.revocations = revocations
        # Out-of-band human approvals for afa.required. The agent has no path
        # to this store; approvals arrive on the principal's endpoint.
        self.approvals = approvals
        self.merchant_keyring = merchant_keyring or MerchantKeyring()
        self._hash = policy_hash(policy)
        self._eval_lock = threading.Lock()
        self._spent_jtis: set[str] = set()

    def _state(self) -> AccumulatedState:
        if self.ledger is not None:
            return self.ledger.state()
        return AccumulatedState()

    def _resolve_to_action(
        self, prop: Proposal | Action, now: datetime | None = None
    ) -> tuple[ResolvedAction, ClauseResult | None]:
        """Resolve an untrusted wire proposal into an authoritative ResolvedAction.

        Every price, title, category and total comes from the price book, unless a
        valid merchant-signed quote is presented for the line. Invariant: quote sets
        unit_price only; title, existence and category come from the price book.
        """
        if self.pricebook is None:
            raise PriceBookMissing(
                "gateway has no price book; it cannot resolve a proposal without "
                "reading agent-supplied prices, so it refuses"
            )

        items: list[ResolvedLineItem] = []
        has_quote = False
        last_quote_price = 0
        for it in prop.items:
            pb = self.pricebook.lookup(it.sku)   # KeyError on an unknown SKU
            unit_price = pb.unit_price
            if getattr(it, "quote", None) is not None:
                has_quote = True
                quoted_price = verify_quote(
                    it.quote,
                    expected_merchant=prop.merchant,
                    expected_sku=it.sku,
                    keyring=self.merchant_keyring,
                    now=now or datetime.now(UTC),
                )
                if quoted_price != int(pb.unit_price):
                    raise QuoteDisagrees(
                        f"quote price \u20b9{quoted_price/100:.2f} disagrees with price book \u20b9{int(pb.unit_price)/100:.2f}",
                        observed=quoted_price,
                        expected=int(pb.unit_price),
                    )
                last_quote_price = quoted_price
                unit_price = Paise(quoted_price)

            items.append(
                ResolvedLineItem(
                    sku=pb.sku,
                    title=pb.title,
                    qty=it.qty,
                    unit_price=unit_price,
                    amount=Paise(it.qty * int(unit_price)),
                    category=pb.category,
                )
            )
        total = Paise(sum(int(i.amount) for i in items))
        action = ResolvedAction(
            type=prop.type,
            amount=total,
            merchant=prop.merchant,
            items=items,
            attempt=prop.attempt,
            downstream_ref=prop.downstream_ref,
            capability=getattr(prop, "capability", None),
        )
        quote_clause = None
        if has_quote:
            quote_clause = ClauseResult(
                id="quote.confirmed",
                result=Verdict.ALLOW,
                observed=last_quote_price,
                limit=last_quote_price,
                detail="merchant quote confirmed against price book",
            )
        return action, quote_clause

    def _resolve_raw_to_action(self, prop: RawProposal) -> tuple[ResolvedAction, None]:
        """Identity-resolve a raw proposal. Same discipline, different source of truth.

        There is no catalog behind `create_payment_link(amount=...)`, so there is
        nothing to look the figure up in: the request is the action. What must
        hold is not "no agent field is read" but "the checked figure is the
        executed figure", and that is made structural here rather than promised.

        `prop.amount` is read exactly once, on this line, and written to
        `ResolvedAction.amount`. Every constraint reads the resolved action, and
        the forwarder rebuilds the upstream arguments from it. The agent's own
        argument dict is discarded after this point and never consulted again.
        """
        return (
            ResolvedAction(
                type=prop.type,
                amount=prop.amount,
                merchant=prop.merchant,
                items=[],
                downstream_ref=prop.ref,
            ),
            None,
        )

    def _resolve(self, action: ResolvedAction) -> tuple[str | None, dict[str, str | None]]:
        if self.resolver is None:
            return action.merchant, {i.sku: i.category for i in action.items}
        return (
            self.resolver.merchant(action.merchant),
            {i.sku: self.resolver.category(i.sku, i.title) for i in action.items},
        )

    def _verify_token(self, token: str | None, now: datetime) -> str | None:
        """Request path step 1. Returns the jti, or raises TokenRejected.

        A gateway configured with an issuer public key requires a token on every
        call. A gateway configured without one is running in the in-process trust
        domain (the harness) and skips the check, which is why the service refuses
        to start without a key.
        """
        if self.issuer_public_key is None:
            return None
        if not token:
            raise TokenRejected("no agent token presented")
        try:
            claims = verify_agent_token(token, self.issuer_public_key, now=now)
        except (SignatureInvalid, TokenError) as e:
            raise TokenRejected(str(e)) from e
        if claims.mandate_id != self.policy.mandate_id:
            raise TokenRejected(
                f"token is bound to {claims.mandate_id}, this gateway serves "
                f"{self.policy.mandate_id}"
            )
        if self.revocations is not None and (
            self.revocations.is_revoked(claims.jti)
            or self.revocations.is_revoked(claims.mandate_id)
        ):
            raise TokenRejected(f"jti {claims.jti} is revoked")
        return claims.jti

    def _void_order(self, body: dict | None) -> bool:
        """Pull a divergent order back off the rail. True only if the rail agreed.

        Fails closed on purpose. A downstream with no `void_order`, a missing
        order id, or a rail that refuses all report False, and the caller then
        records that the order stands. Claiming a void that did not happen would
        make the audit log say money came back when it did not.
        """
        order_id = (body or {}).get("id")
        if not order_id:
            return False
        void = getattr(self.downstream, "void_order", None)
        if void is None:
            return False
        try:
            void(order_id)
        except (DownstreamError, DownstreamTimeout):
            return False
        return True

    def propose(
        self,
        proposal: Proposal | Action | RawProposal,
        now: datetime,
        token: str | None = None,
    ) -> Decision:
        with self._eval_lock:
            # 1. Token before anything else. An unauthenticated caller learns
            #    nothing about the price book or the policy.
            try:
                self._verify_token(token, now)
            except TokenRejected as e:
                return Decision(
                    verdict=Verdict.DENY,
                    clause_id="authentication",
                    message=str(e),
                )

            # 2. Resolve references into facts.
            quote_clause: ClauseResult | None = None
            try:
                if isinstance(proposal, RawProposal):
                    action, _ = self._resolve_raw_to_action(proposal)
                else:
                    action, quote_clause = self._resolve_to_action(proposal, now)
            except QuoteError as e:
                action, _ = self._resolve_to_action(_strip_quotes(proposal), now)
                quote_clause = ClauseResult(
                    id=e.clause_id,
                    result=Verdict.DENY,
                    observed=e.observed,
                    limit=e.expected,
                    detail=str(e),
                )
            except KeyError as e:
                return Decision(
                    verdict=Verdict.DENY,
                    clause_id="pricebook",
                    message=f"unknown SKU: {e}",
                )
            except PriceBookMissing as e:
                return Decision(
                    verdict=Verdict.DENY,
                    clause_id="pricebook",
                    message=str(e),
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
            # Keyed on the resolved intent, so an approval for one basket cannot
            # authorise a different basket of the same value.
            approved = (
                self.approvals.is_approved(idem) if self.approvals is not None else False
            )
            ctx = EvalContext(
                action=action,
                policy=self.policy,
                state=self._state(),
                now=now,
                resolved_merchant=merchant,
                resolved_categories=categories,
                afa_approved=approved,
            )
            clauses = evaluate_all(ctx)
            if quote_clause is not None:
                clauses.insert(0, quote_clause)
            verdict = combine(clauses)
            blocking = first_blocking(clauses)

            may_execute = verdict is Verdict.ALLOW or self.mode is Mode.OBSERVE
            if may_execute and self.ledger is not None:
                self.ledger.open_pending(idem, action, now)

        downstream_body, executed, final = None, False, verdict
        cap = None

        if may_execute:
            try:
                # `action`, never `proposal`. A downstream that could see the
                # proposal could execute a figure the constraints never saw,
                # which is the whole failure this class exists to remove. Same
                # rule `OrderStore.record()` already follows.
                downstream_body = self.downstream.create_order(
                    action.amount,
                    receipt=idem,
                    notes={"mandate_id": self.policy.mandate_id},
                    skus=[i.sku for i in action.items],
                    action=action,
                )
                downstream_amt = downstream_body.get("amount") if downstream_body else None
                if downstream_amt is not None and int(downstream_amt) != int(action.amount):
                    final = Verdict.UNKNOWN
                    executed = False
                    # Detecting the overcharge is not containing it. The order
                    # exists on the rail the moment create_order returns, so
                    # withholding the capability leaves the money moved. Pull it
                    # back, and say in the clause whether that worked.
                    voided = self._void_order(downstream_body)
                    if voided:
                        downstream_body = {**downstream_body, "status": "voided", "voided": True}
                    div_clause = ClauseResult(
                        id="rail.divergence",
                        result=Verdict.UNKNOWN,
                        observed=int(downstream_amt),
                        limit=int(action.amount),
                        detail=(
                            f"downstream rail amount ₹{int(downstream_amt)/100:.2f} diverges from "
                            f"authorized amount ₹{int(action.amount)/100:.2f}; "
                            + ("order voided on the rail" if voided
                               else "VOID FAILED, the order stands on the rail")
                        ),
                    )
                    clauses.append(div_clause)
                    if self.ledger is not None:
                        self.ledger.mark_failed(idem, f"rail divergence: downstream={downstream_amt}, authorized={action.amount}, voided={voided}")
                else:
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
        blocking = first_blocking(clauses)
        clause_id = (
            str(blocking.id)
            if blocking
            else (None if final is Verdict.ALLOW else "downstream")
        )
        msg = _explain(blocking) if blocking else str(final)
        if any(c.id == "rail.divergence" for c in clauses):
            clause_id = "rail.divergence"
            div_c = next(c for c in clauses if c.id == "rail.divergence")
            msg = div_c.detail

        return Decision(
            verdict=final,
            clause_id=clause_id,
            message=msg,
            idem_key=idem,
            downstream=downstream_body,
            executed=executed,
            capability=cap,
        )

    def capture_payment(
        self,
        order_id: str,
        amount: int,
        capability: str,
        idem_key: str,
        token: str | None = None,
        now: datetime | None = None,
    ) -> Decision:
        """Capture against an authorised order. The capability is the authorisation.

        The HMAC binds (idem_key, authorised_amount, order_id), so a capture for
        any other amount cannot present a valid capability. This is the fix for
        price.flip#004, where a legal Rs 881 order settled at Rs 8,810: the gateway
        used to validate the action it was shown and never reconcile what settled.
        """
        now = now or datetime.now(UTC)
        try:
            self._verify_token(token, now)
        except TokenRejected as e:
            return Decision(verdict=Verdict.DENY, clause_id="authentication", message=str(e))

        if not verify_capture_capability(
            capability, idem_key, int(amount), order_id, self.capability_secret
        ):
            return Decision(
                verdict=Verdict.DENY,
                clause_id="capture.binding",
                idem_key=idem_key,
                message=(
                    f"capture capability does not authorise {amount} paise on "
                    f"{order_id}; the authorised amount is the only one it signs"
                ),
            )

        with self._eval_lock:
            if capability in self._spent_jtis:
                return Decision(
                    verdict=Verdict.DENY,
                    clause_id="capture.replay",
                    idem_key=idem_key,
                    message="this capture capability has already been spent",
                )
            self._spent_jtis.add(capability)

        body = self.downstream.capture_payment(order_id, Paise(int(amount)))
        return Decision(
            verdict=Verdict.ALLOW,
            idem_key=idem_key,
            downstream=body if isinstance(body, dict) else {"result": body},
            executed=True,
            message="captured at the authorised amount",
        )
