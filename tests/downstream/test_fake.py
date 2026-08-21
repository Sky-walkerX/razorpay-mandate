import pytest
from mandate.money import rupees
from mandate.downstream.fake import FakeDownstream, DownstreamTimeout

def test_create_order_returns_id_and_is_findable():
    d = FakeDownstream()
    o = d.create_order(rupees(500), receipt="rcpt_a", notes={})
    assert o["id"].startswith("order_")
    assert d.find_orders_by_receipt("rcpt_a") == [o]

def test_fail_next_timeout_raises_but_still_creates_the_order():
    """A timeout means we never learned the outcome, not that nothing happened."""
    d = FakeDownstream()
    d.fail_next("timeout")
    with pytest.raises(DownstreamTimeout):
        d.create_order(rupees(500), receipt="rcpt_b", notes={})
    assert len(d.find_orders_by_receipt("rcpt_b")) == 1

def test_fail_next_applies_once_only():
    d = FakeDownstream()
    d.fail_next("timeout")
    with pytest.raises(DownstreamTimeout):
        d.create_order(rupees(100), receipt="r1", notes={})
    assert d.create_order(rupees(100), receipt="r2", notes={})["id"]
