"""What the agent proposes. Validated arithmetic, canonical intent for idempotency."""
import hashlib
import json
from enum import StrEnum

from pydantic import BaseModel, model_validator

from mandate.money import Paise


class ActionType(StrEnum):
    CREATE_ORDER = "create_order"
    CAPTURE_PAYMENT = "capture_payment"
    CREATE_PAYMENT_LINK = "create_payment_link"


class LineItem(BaseModel):
    sku: str
    title: str
    qty: int
    unit_price: Paise
    amount: Paise

    @model_validator(mode="after")
    def _check(self) -> "LineItem":
        if self.qty < 1:
            raise ValueError("qty must be at least 1")
        if self.amount != self.qty * self.unit_price:
            raise ValueError(f"line amount {self.amount} != qty*unit_price "
                             f"{self.qty * self.unit_price}")
        return self


class Action(BaseModel):
    type: ActionType
    amount: Paise
    currency: str = "INR"
    merchant: str
    items: list[LineItem] = []
    attempt: int = 1
    downstream_ref: str | None = None

    @model_validator(mode="after")
    def _check(self) -> "Action":
        if self.items and self.amount != sum(i.amount for i in self.items):
            raise ValueError(f"action amount {self.amount} != sum of lines "
                             f"{sum(i.amount for i in self.items)}")
        return self


def canonical_intent(a: Action) -> str:
    """A stable fingerprint of *what* is being bought, excluding retry bookkeeping."""
    body = {
        "type": str(a.type),
        "amount": int(a.amount),
        "currency": a.currency,
        "merchant": a.merchant,
        "items": sorted(
            [{"sku": i.sku, "qty": i.qty, "unit_price": int(i.unit_price)} for i in a.items],
            key=lambda d: d["sku"]),
    }
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
