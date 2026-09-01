"""Render a Mandate Policy as an AP2 v0.2 Open Checkout Mandate credential."""

from mandate.ap2.schema import (
    AP2CheckoutMandate,
    AP2CheckoutSpec,
    AP2LineItem,
    AP2MandateExtensions,
)
from mandate.policy.models import ConstraintId as C
from mandate.policy.models import Policy

CONSTRAINT_AP2_MAPPING: dict[C, tuple[str, str]] = {
    C.MERCHANT_ALLOW: ("native", "checkout.allowed_merchants"),
    C.QUANTITY_MAX_PER_ITEM: ("partial", "checkout.line_items.max_quantity"),
    C.BUDGET_TOTAL: ("extension", "extensions.budget_total_paise"),
    C.BUDGET_PER_TRANSACTION: ("extension", "extensions.budget_per_transaction_paise"),
    C.BUDGET_PER_ITEM: ("extension", "extensions.budget_per_item_paise"),
    C.CATEGORY_DENY: ("extension", "extensions.category_deny"),
    C.ITEM_DENY_RECENT: ("extension", "extensions.item_deny_recent"),
    C.VELOCITY: ("extension", "extensions.velocity_max_actions"),
    C.TIME_WINDOW: ("extension", "extensions.time_window_start"),
}


def render_ap2_mandate(policy: Policy) -> AP2CheckoutMandate:
    """Map a Policy AST into an AP2 v0.2 Checkout Mandate model."""
    c = policy.constraints

    # 1. Merchants (Native)
    merchants = c.get(C.MERCHANT_ALLOW, [])
    if isinstance(merchants, str):
        merchants = [merchants]

    # 2. Line Items (Partial)
    max_qty = c.get(C.QUANTITY_MAX_PER_ITEM, {}).get("max") if C.QUANTITY_MAX_PER_ITEM in c else None
    max_unit_price = c.get(C.BUDGET_PER_ITEM, {}).get("max") if C.BUDGET_PER_ITEM in c else None

    line_items = [
        AP2LineItem(sku="*", max_quantity=max_qty, max_unit_price_paise=max_unit_price)
    ]

    # 3. Extensions
    extensions = AP2MandateExtensions(
        budget_total_paise=c.get(C.BUDGET_TOTAL, {}).get("max") if C.BUDGET_TOTAL in c else None,
        budget_per_transaction_paise=c.get(C.BUDGET_PER_TRANSACTION, {}).get("max") if C.BUDGET_PER_TRANSACTION in c else None,
        budget_per_item_paise=c.get(C.BUDGET_PER_ITEM, {}).get("max") if C.BUDGET_PER_ITEM in c else None,
        category_deny=c.get(C.CATEGORY_DENY, []),
        item_deny_recent=c.get(C.ITEM_DENY_RECENT, []),
        velocity_max_actions=c.get(C.VELOCITY, {}).get("max_actions") if C.VELOCITY in c else None,
        velocity_window_seconds=c.get(C.VELOCITY, {}).get("window_seconds") if C.VELOCITY in c else None,
    )

    checkout_spec = AP2CheckoutSpec(
        allowed_merchants=list(merchants),
        line_items=line_items,
    )

    return AP2CheckoutMandate(
        mandate_id=policy.mandate_id,
        principal=policy.principal,
        agent=policy.agent,
        iat=policy.issued,
        exp=policy.expires,
        checkout=checkout_spec,
        extensions=extensions,
    )

