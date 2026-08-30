from datetime import datetime

import pytest

from mandate.compiler.compile import IST
from mandate.money import rupees
from mandate.policy.models import CompilerInfo, Policy, Provenance
from mandate.policy.models import ConstraintId as C


@pytest.fixture
def policy_all_nine() -> Policy:
    """A policy that exercises every constraint an attack family targets."""
    base = {
        C.BUDGET_TOTAL: {"max": int(rupees(2000))},
        C.BUDGET_PER_TRANSACTION: {"max": int(rupees(1000))},
        C.BUDGET_PER_ITEM: {"max": int(rupees(500))},
        C.MERCHANT_ALLOW: ["zepto", "blinkit", "instamart"],
        C.CATEGORY_DENY: ["alcohol"],
        C.QUANTITY_MAX_PER_ITEM: {"max": 5},
        C.VELOCITY: {"max_actions": 3, "window": "mandate"},
        C.TIME_WINDOW: {},
    }
    return Policy(
        mandate_id="mnd_test",
        principal="user_local",
        agent="agt_shopper",
        issued=datetime(2026, 9, 1, 9, 0, tzinfo=IST),
        expires=datetime(2026, 9, 1, 19, 30, tzinfo=IST),
        source_text="test",
        constraints=base,
        provenance=Provenance(stated=list(base.keys()), inferred=[]),
        compiler=CompilerInfo(model="claude-opus-5", temperature=0.0, version="1.0.0"),
    )


class SyntheticPriceBook:
    """Test-double price book that derives a price from the SKU name.

    A SKU of the form ``p_<paise>[_<category>]`` resolves to that unit price, so a
    test can ask for any amount without hand-building a catalog. It is a stand-in
    for a real product source, and the point of it is the same as the real one:
    the price is the gateway's to state, never the agent's.
    """

    def __init__(self, extra: dict | None = None) -> None:
        self._extra = dict(extra or {})

    def _derive(self, sku: str):
        from mandate.gateway.pricebook import PriceBookItem
        from mandate.money import Paise

        parts = sku.split("_")
        if len(parts) < 2 or parts[0] != "p" or not parts[1].isdigit():
            raise KeyError(f"SKU {sku!r} not found in price book")
        category = parts[2] if len(parts) > 2 else "grocery"
        return PriceBookItem(
            sku=sku,
            title=f"Test item {sku}",
            unit_price=Paise(int(parts[1])),
            category=category,
            merchant="zepto",
        )

    def lookup(self, sku: str):
        if sku in self._extra:
            return self._extra[sku]
        return self._derive(sku)

    def has_sku(self, sku: str) -> bool:
        try:
            self.lookup(sku)
            return True
        except KeyError:
            return False


def priced_sku(amount, category: str = "grocery", tag: str = "") -> str:
    """The SKU that SyntheticPriceBook resolves to `amount` paise.

    `tag` makes two SKUs distinct at the same price, which is how a test asks for
    several separate line items that each cost the same.
    """
    return f"p_{int(amount)}_{category}" + (f"_{tag}" if tag else "")
