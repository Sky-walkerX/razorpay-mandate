"""Pydantic models for AP2 v0.2 Open Checkout Mandate SD-JWT credential structures."""
from datetime import datetime

from pydantic import BaseModel, Field

AP2_VCT_CHECKOUT_OPEN = "mandate.checkout.open.1"


class AP2LineItem(BaseModel):
    sku: str
    max_quantity: int | None = None
    max_unit_price_paise: int | None = None


class AP2CheckoutSpec(BaseModel):
    allowed_merchants: list[str] = Field(default_factory=list)
    line_items: list[AP2LineItem] = Field(default_factory=list)


class AP2MandateExtensions(BaseModel):
    budget_total_paise: int | None = None
    budget_per_transaction_paise: int | None = None
    budget_per_item_paise: int | None = None
    category_deny: list[str] = Field(default_factory=list)
    item_deny_recent: list[str] = Field(default_factory=list)
    velocity_max_actions: int | None = None
    velocity_window_seconds: int | None = None
    time_window_start: datetime | None = None
    time_window_end: datetime | None = None


class AP2CheckoutMandate(BaseModel):
    vct: str = AP2_VCT_CHECKOUT_OPEN
    mandate_id: str
    principal: str
    agent: str
    iat: datetime
    exp: datetime
    checkout: AP2CheckoutSpec
    extensions: AP2MandateExtensions

