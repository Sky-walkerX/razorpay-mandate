"""Tests asserting that the quote carve-out is sound.

The one rule: no constraint may read an agent-supplied field.
Carve-out: an agent-supplied field may be read only if the agent cannot forge
what it resolves to. Quotes are Ed25519-signed by the merchant and verified
against an authoritative public keyring before the lattice sees the unit price.
"""
from mandate.adapters.direct import IGNORED_AGENT_FIELDS, UNFORGEABLE_AGENT_FIELDS
from mandate.gateway.action import Proposal, ProposalItem, canonical_intent
from mandate.gateway.quote import MerchantKeyring

STRUCTURAL_FIELDS = {"type", "merchant", "items", "attempt", "downstream_ref"}


def test_every_field_on_the_wire_is_either_ignored_or_unforgeable():
    """Assert every field on Proposal and ProposalItem is classified."""
    wire_fields = set(Proposal.model_fields.keys()) | set(ProposalItem.model_fields.keys())
    classified = set(IGNORED_AGENT_FIELDS) | set(UNFORGEABLE_AGENT_FIELDS.keys()) | STRUCTURAL_FIELDS
    unclassified = wire_fields - classified
    assert not unclassified, (
        f"Found unclassified field(s) on wire models: {unclassified}. "
        "Every field must be ignored or unforgeable."
    )


def test_the_gateway_holds_no_merchant_private_key():
    """MerchantKeyring must hold public keys only and expose no signing methods."""
    keyring = MerchantKeyring()
    for attr in dir(keyring):
        assert "private" not in attr.lower(), f"MerchantKeyring exposes private key attribute: {attr}"
        assert "sign" not in attr.lower(), f"MerchantKeyring exposes signing method: {attr}"


def test_canonical_intent_does_not_hash_quote():
    """canonical_intent must be byte-identical whether quote is absent or present."""
    prop_no_quote = Proposal(
        merchant="zepto",
        items=[ProposalItem(sku="sku_01", qty=2, quote=None)],
    )
    prop_quote_a = Proposal(
        merchant="zepto",
        items=[ProposalItem(sku="sku_01", qty=2, quote="quote_payload_a.sig_hex_a")],
    )
    prop_quote_b = Proposal(
        merchant="zepto",
        items=[ProposalItem(sku="sku_01", qty=2, quote="quote_payload_b.sig_hex_b")],
    )

    hash_no_quote = canonical_intent(prop_no_quote)
    hash_quote_a = canonical_intent(prop_quote_a)
    hash_quote_b = canonical_intent(prop_quote_b)

    assert hash_no_quote == hash_quote_a == hash_quote_b

