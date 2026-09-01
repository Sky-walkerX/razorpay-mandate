import pytest

from mandate.downstream.razorpay import RazorpayDownstream


def test_refuses_live_keys():
    with pytest.raises(ValueError, match="test mode"):
        RazorpayDownstream(key_id="rzp_live_abc123", key_secret="s")

def test_accepts_test_keys():
    assert RazorpayDownstream(key_id="rzp_test_abc123", key_secret="s") is not None


def test_the_receipt_is_cut_to_what_the_rail_accepts():
    """Razorpay caps `receipt` at 56 characters and `canonical_intent()` returns
    64, so before this every order against the real rail came back as a DENY on
    the `downstream` clause."""
    from mandate.downstream.razorpay import MAX_RECEIPT_CHARS, _receipt

    idem = "a" * 64
    assert len(_receipt(idem)) == MAX_RECEIPT_CHARS
    assert _receipt(idem) == idem[:MAX_RECEIPT_CHARS]


def test_a_short_receipt_is_left_alone():
    from mandate.downstream.razorpay import _receipt

    assert _receipt("short_receipt") == "short_receipt"


def test_lookup_truncates_the_same_way_it_wrote(monkeypatch):
    """Reconciliation compares against what was actually stored on the rail."""
    client = RazorpayDownstream(key_id="rzp_test_abc123", key_secret="s")
    idem = "b" * 64
    monkeypatch.setattr(
        client, "_c",
        type("C", (), {"order": type("O", (), {
            "all": staticmethod(lambda _p: {"items": [{"receipt": idem[:56], "id": "order_1"}]})
        })()})(),
    )
    assert [o["id"] for o in client.find_orders_by_receipt(idem)] == ["order_1"]
