"""What the agent proposes (Proposal) and what the gateway derives (ResolvedAction).

The agent's proposal contains references only: {sku, qty, merchant}.
The gateway dereferences prices, titles, categories, and totals from its price book.
"""
import hashlib
import json
from enum import StrEnum

from pydantic import BaseModel, model_validator

from mandate.money import Paise


class ActionType(StrEnum):
    CREATE_ORDER = "create_order"
    CAPTURE_PAYMENT = "capture_payment"
    CREATE_PAYMENT_LINK = "create_payment_link"


class ProposalItem(BaseModel):
    """Untrusted wire item sent by the agent. No prices, no titles, no totals."""
    sku: str
    qty: int = 1

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
    """A stable fingerprint of intent, invariant under agent-steered fields."""
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
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()

