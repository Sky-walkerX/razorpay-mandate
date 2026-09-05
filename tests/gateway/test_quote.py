"""Unit tests for Ed25519 merchant-signed quote verification."""
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from mandate.gateway.quote import (
    MerchantKeyring,
    QuoteExpired,
    QuoteMalformed,
    QuoteMerchantMismatch,
    QuoteNotYetValid,
    QuoteSignatureInvalid,
    QuoteSkuMismatch,
    QuoteUnsigned,
    mint_quote,
    verify_quote,
)
from mandate.policy.crypto import generate_keypair

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def keys():
    priv, pub = generate_keypair()
    return priv, pub


@pytest.fixture
def keyring(keys):
    _, pub = keys
    return MerchantKeyring({"zepto": [pub]})


def test_valid_quote_verifies_and_returns_paise(keys, keyring):
    priv, _ = keys
    q = mint_quote(
        merchant="zepto",
        sku="sku_123",
        unit_price_paise=45000,
        private_key_hex=priv,
        issued=NOW - timedelta(minutes=1),
        expires=NOW + timedelta(minutes=14),
    )
    price = verify_quote(q, expected_merchant="zepto", expected_sku="sku_123", keyring=keyring, now=NOW)
    assert price == 45000


def test_quote_malformed_envelope(keyring):
    with pytest.raises(QuoteMalformed):
        verify_quote("not_a_valid_envelope", "zepto", "sku_123", keyring, NOW)


def test_quote_unknown_merchant(keys):
    priv, _ = keys
    q = mint_quote("unknown_merchant", "sku_123", 50000, priv, issued=NOW, expires=NOW + timedelta(minutes=5))
    empty_ring = MerchantKeyring()
    with pytest.raises(QuoteUnsigned):
        verify_quote(q, "unknown_merchant", "sku_123", empty_ring, NOW)


def test_quote_invalid_signature(keys, keyring):
    other_priv, _ = generate_keypair()
    # Signed with wrong key
    q = mint_quote("zepto", "sku_123", 50000, other_priv, issued=NOW, expires=NOW + timedelta(minutes=5))
    with pytest.raises(QuoteSignatureInvalid):
        verify_quote(q, "zepto", "sku_123", keyring, NOW)


def test_quote_merchant_mismatch(keys, keyring):
    priv, _ = keys
    # Signed for zepto, but proposed for blinkit
    q = mint_quote("zepto", "sku_123", 50000, priv, issued=NOW, expires=NOW + timedelta(minutes=5))
    with pytest.raises(QuoteMerchantMismatch):
        verify_quote(q, "blinkit", "sku_123", keyring, NOW)


def test_quote_sku_mismatch(keys, keyring):
    priv, _ = keys
    # Signed for sku_other, but proposed for sku_123
    q = mint_quote("zepto", "sku_other", 50000, priv, issued=NOW, expires=NOW + timedelta(minutes=5))
    with pytest.raises(QuoteSkuMismatch):
        verify_quote(q, "zepto", "sku_123", keyring, NOW)


def test_quote_unsupported_currency(keys, keyring):
    priv, _ = keys
    q = mint_quote("zepto", "sku_123", 50000, priv, currency="USD", issued=NOW, expires=NOW + timedelta(minutes=5))
    with pytest.raises(QuoteMalformed):
        verify_quote(q, "zepto", "sku_123", keyring, NOW)


def test_quote_expired(keys, keyring):
    priv, _ = keys
    q = mint_quote("zepto", "sku_123", 50000, priv, issued=NOW - timedelta(hours=1), expires=NOW - timedelta(minutes=1))
    with pytest.raises(QuoteExpired):
        verify_quote(q, "zepto", "sku_123", keyring, NOW)


def test_quote_not_yet_valid(keys, keyring):
    priv, _ = keys
    q = mint_quote("zepto", "sku_123", 50000, priv, issued=NOW + timedelta(minutes=5), expires=NOW + timedelta(hours=1))
    with pytest.raises(QuoteNotYetValid):
        verify_quote(q, "zepto", "sku_123", keyring, NOW)


def test_quote_max_age_enforced(keys, keyring):
    priv, _ = keys
    q = mint_quote("zepto", "sku_123", 50000, priv, issued=NOW - timedelta(minutes=20), expires=NOW + timedelta(hours=1))
    with pytest.raises(QuoteExpired):
        verify_quote(q, "zepto", "sku_123", keyring, NOW, max_age=timedelta(minutes=15))



def test_the_gateway_bounds_quote_age_regardless_of_what_the_merchant_signed():
    """A shop does not get to set the gateway's freshness policy.

    `expires` is the merchant's claim about its own quote. A merchant that stamps it
    a year out -- by mistake, or because its signing service was compromised once --
    would otherwise mint a price good for a year. The gateway's own ceiling is
    applied on top and is the one that binds.
    """
    priv, pub = generate_keypair()
    ring = MerchantKeyring({"zepto": [pub]})
    issued = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
    quote = mint_quote(
        "zepto", "sku_01", 50000, priv,
        issued=issued, expires=issued + timedelta(days=365),
    )

    # Inside the ceiling: honoured, even though the merchant said a year.
    assert verify_quote(quote, "zepto", "sku_01", ring,
                        now=issued + timedelta(minutes=5),
                        max_age=timedelta(minutes=15)) == 50000

    # Past the ceiling: refused, even though the merchant's own expiry is months away.
    with pytest.raises(QuoteExpired):
        verify_quote(quote, "zepto", "sku_01", ring,
                     now=issued + timedelta(minutes=16),
                     max_age=timedelta(minutes=15))


def test_a_keyring_file_that_is_not_an_object_refuses_every_quote():
    """It used to return None and crash the caller on the next attribute access."""
    import json
    import tempfile

    d = Path(tempfile.mkdtemp())
    bad = d / "merchants.json"
    bad.write_text(json.dumps(["zepto", "blinkit"]))
    ring = MerchantKeyring.from_file(bad)
    assert isinstance(ring, MerchantKeyring)
    assert ring.has_merchant("zepto") is False
