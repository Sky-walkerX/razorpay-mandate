import pytest
from mandate.downstream.razorpay import RazorpayDownstream

def test_refuses_live_keys():
    with pytest.raises(ValueError, match="test mode"):
        RazorpayDownstream(key_id="rzp_live_abc123", key_secret="s")

def test_accepts_test_keys():
    assert RazorpayDownstream(key_id="rzp_test_abc123", key_secret="s") is not None
