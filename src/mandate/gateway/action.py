"""What the agent proposes (Proposal) and what the gateway derives (ResolvedAction).

The agent's proposal contains references only: {sku, qty, merchant}.
The gateway dereferences prices, titles, categories, and totals from its price book.
"""
import hashlib
import json
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, model_validator

from mandate.money import Paise


class ActionType(StrEnum):
    CREATE_ORDER = "create_order"
    CAPTURE_PAYMENT = "capture_payment"
    CREATE_PAYMENT_LINK = "create_payment_link"
    # Razorpay's own MCP server names this tool separately from the standard
    # payment link. The proxy forwards to whichever the action names, so the
    # names have to line up with the upstream's.
    PAYMENT_LINK_UPI_CREATE = "payment_link_upi_create"


class ProposalItem(BaseModel):
    """Untrusted wire item sent by the agent. No prices, no titles, no totals."""
    sku: str
    qty: int = 1
    quote: str | None = None

    @model_validator(mode="after")
    def _check(self) -> "ProposalItem":
        if self.qty < 1:
            raise ValueError("qty must be at least 1")
        return self


class Proposal(BaseModel):
    """Untrusted wire payload sent by the agent."""
    type: ActionType = ActionType.CREATE_ORDER
    merchant: str = "grocery"
    items: list[ProposalItem] = []
    attempt: int = 1
    downstream_ref: str | None = None
    capability: str | None = None


class RawProposal(BaseModel):
    """An agent's proposal with no catalog behind it.

    Razorpay's own tools take a raw amount: `create_payment_link(amount=...)` has
    no SKU, no price book, and no truth for the gateway to look up. The request
    *is* the action.

    This is deliberately a separate type from `Proposal` rather than a field on
    it. `Proposal` carries references only, and the `IGNORED_AGENT_FIELDS`
    property test hangs off that fact; adding an `amount` there would quietly
    weaken a guard that exists to catch exactly this.

    What holds instead is that the checked figure is the executed figure.
    `Gateway._resolve_raw_to_action` reads `amount` exactly once and writes it to
    `ResolvedAction.amount`, and the forwarder rebuilds the upstream call from
    the resolved action. The agent's own argument dict is never read again.
    """
    model_config = ConfigDict(extra="ignore")

    type: ActionType
    tool: str
    amount: Paise
    merchant: str = "self"
    # The one non-money argument that survives resolution, because
    # `capture_payment` is meaningless without the payment it captures. It is an
    # opaque rail reference, never a figure, and no constraint reads it.
    ref: str | None = None


class ResolvedLineItem(BaseModel):
    """Authoritative line item dereferenced from the price book."""
    sku: str
    title: str
    qty: int
    unit_price: Paise
    amount: Paise
    category: str = "grocery"

    @model_validator(mode="after")
    def _check(self) -> "ResolvedLineItem":
        if self.qty < 1:
            raise ValueError("qty must be at least 1")
        if self.amount != self.qty * self.unit_price:
            raise ValueError(
                f"line amount {self.amount} != qty*unit_price {self.qty * self.unit_price}"
            )
        return self


# Backward-compatible alias
LineItem = ResolvedLineItem


class ResolvedAction(BaseModel):
    """Authoritative action evaluated by the gateway and executed downstream."""
    type: ActionType
    amount: Paise
    currency: str = "INR"
    merchant: str
    resolved_merchant: str | None = None
    items: list[ResolvedLineItem] = []
    attempt: int = 1
    downstream_ref: str | None = None
    capability: str | None = None

    @model_validator(mode="after")
    def _check(self) -> "ResolvedAction":
        if self.items and self.amount != sum(i.amount for i in self.items):
            raise ValueError(
                f"action amount {self.amount} != sum of lines {sum(i.amount for i in self.items)}"
            )
        return self


# Backward-compatible alias
Action = ResolvedAction


def canonical_intent(a: Action | Proposal, mandate_id: str = "") -> str:
    """A stable fingerprint of intent, invariant under agent-steered fields.

    For a basket the amount is derived from the items, so hashing the items is
    hashing the money and adding the amount would let an agent steer the key by
    a paisa. That is `idem.forge`, and the invariance property test exists to
    keep it dead.

    A raw action has no items, and then the amount is the whole intent: a Rs 100
    payment link and a Rs 50,000 payment link are different requests. Without
    this branch they share a key and the second replays the first as "already
    committed", which is a far worse failure than a steerable key.

    The amount is added ONLY when there are no items, so every hash this function
    has ever returned for an item-bearing action is byte-identical.
    """
    items = sorted(
        [{"qty": i.qty, "sku": i.sku} for i in a.items],
        key=lambda d: d["sku"],
    )
    body = {
        "mandate_id": mandate_id,
        "type": str(a.type),
        "merchant": a.merchant.strip().lower() if a.merchant else "",
        "items": items,
    }
    if not items:
        body["amount"] = int(getattr(a, "amount", 0) or 0)
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()

