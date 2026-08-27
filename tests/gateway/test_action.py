import pytest

from mandate.gateway.action import Action, ActionType, LineItem, canonical_intent
from mandate.money import rupees


def _item(sku="sku_0001", qty=1, unit=None):
    if unit is None:
        unit = rupees(80)
    return LineItem(sku=sku, title="Toor Dal", qty=qty, unit_price=unit,
                    amount=rupees(80 * qty))

def _action(**over):
    base = {"type": ActionType.CREATE_ORDER, "amount": rupees(80), "currency": "INR",
            "merchant": "zepto", "items": [_item()]}
    return Action(**(base | over))

def test_line_amount_must_equal_qty_times_unit_price():
    with pytest.raises(ValueError, match="line amount"):
        LineItem(sku="s", title="t", qty=2, unit_price=rupees(80), amount=rupees(80))

def test_action_amount_must_equal_sum_of_lines():
    with pytest.raises(ValueError, match="action amount"):
        _action(amount=rupees(999))

def test_canonical_intent_ignores_attempt_number():
    assert canonical_intent(_action(attempt=1)) == canonical_intent(_action(attempt=5))

def test_canonical_intent_changes_with_amount():
    a = _action()
    b = _action(amount=rupees(160), items=[_item(qty=2)])
    assert canonical_intent(a) != canonical_intent(b)

def test_canonical_intent_is_order_independent_across_lines():
    x = _action(amount=rupees(160), items=[_item("sku_a"), _item("sku_b")])
    y = _action(amount=rupees(160), items=[_item("sku_b"), _item("sku_a")])
    assert canonical_intent(x) == canonical_intent(y)

def test_non_inr_is_representable_but_flagged_downstream():
    """The model allows it; the currency constraint denies it. Separation of concerns."""
    assert _action(currency="USD").currency == "USD"
